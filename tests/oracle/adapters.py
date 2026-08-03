import json
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ElementTree
from abc import ABC, abstractmethod
from importlib.util import find_spec
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from patos import FrozenModel

from mcmr.domain.contracts import RuleValue

from .contracts import Diagnostic, Report, Site

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


class Oracle(FrozenModel, ABC):
    """Run one upstream tool over one tree and read its own output back as located findings.

    A tool arrives as a subclass registering itself under the name a rule reference spells, so the
    harness gains one without any comparison learning how that tool is invoked or how it writes
    what it found. Each subclass also owns whatever the tool needs before it will run at all, such
    as the compilation database clang-tidy wants and the flat configuration ESLint wants, since
    that is a fact about the tool rather than about the source either reader is looking at.
    """

    tool: ClassVar[str]
    binary: ClassVar[str]
    oracles: ClassVar[dict[str, type["Oracle"]]] = {}

    rules: list[str] = []

    def __init_subclass__(cls) -> None:
        """Register one adapter under the tool it runs."""
        super().__init_subclass__()
        Oracle.oracles[cls.tool] = cls

    @property
    def name(self) -> str:
        """Return the tool and the rules this adapter asked it for."""
        return " ".join((self.tool, *self.rules))

    @classmethod
    def installed(cls, tool: str) -> bool:
        """Whether the program one registered tool needs can be found here."""
        return cls.oracles[tool].present()

    @classmethod
    def of(cls, tool: str, *rules: str) -> Oracle:
        """Return the adapter for one tool, asking it for exactly these rules."""
        return cls.oracles[tool](rules=rules)

    @classmethod
    def present(cls) -> bool:
        """Whether this tool's program is on the path."""
        return shutil.which(cls.binary) is not None

    @abstractmethod
    def diagnostics(self, root: Path) -> list[Diagnostic]:
        """Return every finding this tool reported, read out of its own output."""

    def located(self, root: Path, path: str, line: int) -> Site:
        """Return one reported location as a path relative to the tree, since a name is not one."""
        return Site.at(Path(path).resolve().relative_to(root.resolve()).as_posix(), line)

    def measured(self, found: Diagnostic) -> int:
        """Return how many findings one diagnostic stands for, which is one for a plain report.

        A tool asked for a magnitude states it once and names the number inside its own message, so
        an adapter reading measurements overrides this and every unit becomes one site. That is
        what makes a measurement compare as a multiset, where a reader measuring eleven against
        twelve would otherwise agree by having reported in the same place.
        """
        return 1

    def ran(
        self, command: Sequence[str], directory: Path | None = None
    ) -> subprocess.CompletedProcess[str]:
        """Run one tool, letting a nonzero exit stand since a finding is what causes one.

        A working directory is only ever set by an adapter that needs one, such as Clippy inside
        the crate it builds. Stepping into the tree by default is not harmless: Pylint run from
        inside a package it is reading imports that package's `functools` instead of the standard
        library's and reports nothing at all.
        """
        return subprocess.run(command, capture_output=True, text=True, check=False, cwd=directory)

    def report(self, root: Path) -> Report:
        """Return where this tool reported over one tree."""
        return Report(
            reader=self.name,
            sites=[
                self.located(root, found.path, found.line)
                for found in self.diagnostics(root)
                for _ in range(self.measured(found))
            ],
        )


class PylintOracle(Oracle):
    """Read what Pylint reports for a chosen set of its messages, out of its own JSON report."""

    tool = "pylint"
    binary = "pylint"

    options: list[str] = []

    @classmethod
    def present(cls) -> bool:
        """Whether Pylint is importable, which is how the suite runs it."""
        return find_spec("pylint") is not None

    def diagnostics(self, root: Path) -> list[Diagnostic]:
        """Return every message Pylint reported for the chosen symbols."""
        completed = self.ran(
            [
                sys.executable,
                "-m",
                "pylint",
                "--disable=all",
                f"--enable={','.join(self.rules)}",
                "--output-format=json2",
                "--score=n",
                *self.options,
                str(root),
            ]
        )
        report = json.loads(completed.stdout or '{"messages": []}')
        return [
            Diagnostic(
                path=item["absolutePath"],
                line=item["line"],
                rule=item["symbol"],
                detail=item["message"],
            )
            for item in report["messages"]
        ]


class PylintMagnitudeOracle(PylintOracle):
    """Read the magnitude Pylint measured, not only the place it reported.

    Pylint writes `(12/0)` inside every design message, which is what makes it an oracle for a
    measurement rather than only for a set of places. `options` drives the ceiling to zero so
    nothing is filtered out.
    """

    tool = "pylint magnitude"
    magnitude: ClassVar[re.Pattern[str]] = re.compile(r"\((\d+)/\d+\)")

    def measured(self, found: Diagnostic) -> int:
        """Return the magnitude Pylint wrote inside its own message."""
        stated = self.magnitude.search(found.detail)
        return int(stated.group(1)) if stated is not None else 0


class RuffOracle(Oracle):
    """Read what Ruff reports for a chosen set of its codes, out of its own JSON output.

    Suppressions are read past by default. A `# noqa` says what an author decided rather than what
    the reader saw, and comparing two analyses through two suppression systems compares neither.
    """

    tool = "ruff"
    binary = "ruff"

    respect_suppressions: bool = False

    def diagnostics(self, root: Path) -> list[Diagnostic]:
        """Return every diagnostic Ruff reported for the chosen codes."""
        completed = self.ran(
            [
                "ruff",
                "check",
                "--no-cache",
                "--isolated",
                *([] if self.respect_suppressions else ["--ignore-noqa"]),
                "--select",
                ",".join(self.rules),
                "--output-format",
                "json",
                str(root),
            ]
        )
        return [
            Diagnostic(
                path=item["filename"],
                line=item["location"]["row"],
                rule=item["code"] or "",
                detail=item["message"],
            )
            for item in json.loads(completed.stdout or "[]")
        ]


class ClippyOracle(Oracle):
    """Read what Clippy reports for a chosen set of its lints, out of the compiler's own JSON.

    The lint that produced a diagnostic is read from its code rather than from its prose, so a
    renamed or retired lint answers with nothing instead of quietly matching a sentence.
    """

    tool = "clippy"
    binary = "cargo"

    def diagnostics(self, root: Path) -> list[Diagnostic]:
        """Return every diagnostic one of the chosen lints produced over one crate."""
        completed = self.ran(
            ["cargo", "clippy", "--offline", "--lib", "--message-format", "json"], root
        )
        wanted = {f"clippy::{name}" for name in self.rules}
        return [
            Diagnostic(
                path=str(root / span["file_name"]),
                line=span["line_start"],
                rule=record["message"]["code"]["code"],
                detail=record["message"]["message"],
            )
            for line in completed.stdout.splitlines()
            if (record := json.loads(line))["reason"] == "compiler-message"
            and (record["message"].get("code") or {}).get("code") in wanted
            for span in record["message"]["spans"][:1]
        ]


class ESLintOracle(Oracle):
    """Read what ESLint reports for a chosen set of its rules, out of its own JSON formatter.

    ESLint wants two things before it will answer at all and both are facts about the tool rather
    than about the source. It resolves a flat configuration and every plugin that configuration
    names through Node's own module lookup, so the tree is given a `node_modules` pointing at the
    installation the binary came from and a configuration written beside it. A rule is spelled the
    way ESLint spells it, so a `typescript-eslint` rule arrives under its `@typescript-eslint`
    prefix and is enabled through the plugin rather than through a second tool.
    """

    tool = "eslint"
    binary = "eslint"

    ceiling: int | None = None

    def configure(self, root: Path) -> None:
        """Write the flat configuration and link the packages it imports into the tree."""
        linked = root / "node_modules"
        if not linked.exists():
            linked.symlink_to(self.packages(), target_is_directory=True)
        allowance = "" if self.ceiling is None else f', {{ "max": {self.ceiling} }}'
        enabled = ",\n    ".join(f'"{name}": ["error"{allowance}]' for name in self.rules)
        (root / "eslint.config.mjs").write_text(
            "import tseslint from 'typescript-eslint';\n"
            "export default [\n"
            "  { languageOptions: { ecmaVersion: 'latest', sourceType: 'module' } },\n"
            "  { files: ['**/*.ts'], languageOptions: { parser: tseslint.parser } },\n"
            "  { plugins: { '@typescript-eslint': tseslint.plugin } },\n"
            f"  {{ rules: {{\n    {enabled}\n  }} }},\n"
            "];\n"
        )

    def diagnostics(self, root: Path) -> list[Diagnostic]:
        """Return every message ESLint reported for the chosen rules."""
        self.configure(root)
        completed = self.ran(
            ["eslint", "--no-config-lookup", "--config", "eslint.config.mjs", "--format", "json"],
            root,
        )
        wanted = set(self.rules)
        return [
            Diagnostic(
                path=item["filePath"],
                line=message["line"],
                rule=message["ruleId"],
                detail=message["message"],
            )
            for item in json.loads(completed.stdout or "[]")
            for message in item["messages"]
            if message["ruleId"] in wanted
        ]

    def packages(self) -> Path:
        """Return the `node_modules` directory the installed ESLint was resolved out of."""
        found = shutil.which(self.binary)
        if found is None:
            raise FileNotFoundError("eslint is not installed")
        located = next(
            (parent for parent in Path(found).resolve().parents if parent.name == "node_modules"),
            None,
        )
        if located is None:
            raise FileNotFoundError(f"{found} sits outside any node_modules directory")
        return located


class ESLintMagnitudeOracle(ESLintOracle):
    """Read the magnitude ESLint measured, not only the place it reported.

    A `max-` rule writes the number it counted inside its own message, the way Pylint writes it
    inside a design message, so driving the ceiling to zero and reading that number back makes
    ESLint an oracle for a measurement rather than only for a set of places.
    """

    tool = "eslint magnitude"
    magnitude: ClassVar[re.Pattern[str]] = re.compile(r"\((\d+)\)")

    def measured(self, found: Diagnostic) -> int:
        """Return the magnitude ESLint wrote inside its own message."""
        stated = self.magnitude.search(found.detail)
        return int(stated.group(1)) if stated is not None else 0


class ClangTidyOracle(Oracle):
    """Read what clang-tidy reports for a chosen set of its checks, out of its own diagnostics.

    clang-tidy compiles what it reads, so it wants a compilation database naming every translation
    unit and the flags each is built with. Writing that database is part of running the tool at
    all, which is why it lives here rather than in every fixture that wants an answer.
    """

    tool = "clang-tidy"
    binary = "clang-tidy"
    diagnostic: ClassVar[re.Pattern[str]] = re.compile(
        r"^(?P<path>.+?):(?P<line>\d+):\d+: (?:warning|error): (?P<detail>.*) \[(?P<check>\S+)\]$"
    )
    units: ClassVar[tuple[str, ...]] = (".c", ".cc", ".cpp", ".cxx", ".cu")

    standard: str = "c++23"
    settings: dict[str, str] = {}

    def database(self, root: Path) -> list[Path]:
        """Write the compilation database and return the translation units it names."""
        compiled = sorted(
            path for path in root.rglob("*") if path.suffix in self.units and path.is_file()
        )
        (root / "compile_commands.json").write_text(
            json.dumps(
                [
                    {
                        "directory": str(root.resolve()),
                        "file": str(unit.resolve()),
                        "command": f"clang++ -std={self.standard} -c {unit.resolve()}",
                    }
                    for unit in compiled
                ],
                indent=1,
            )
        )
        return compiled

    def diagnostics(self, root: Path) -> list[Diagnostic]:
        """Return every diagnostic one of the chosen checks produced over one tree."""
        compiled = self.database(root)
        stated = ", ".join(f"{name}: {value}" for name, value in self.settings.items())
        completed = self.ran(
            [
                "clang-tidy",
                "-p",
                ".",
                "--quiet",
                f"--checks=-*,{','.join(self.rules)}",
                f"--config={{CheckOptions: {{{stated}}}}}",
                *(str(unit) for unit in compiled),
            ],
            root,
        )
        wanted = set(self.rules)
        return [
            Diagnostic(
                path=found["path"],
                line=int(found["line"]),
                rule=found["check"],
                detail=found["detail"],
            )
            for line in completed.stdout.splitlines()
            if (found := self.diagnostic.match(line)) is not None
            and wanted.intersection(found["check"].split(","))
        ]


class ClangTidyMagnitudeOracle(ClangTidyOracle):
    """Read the magnitude clang-tidy measured, not only the place it reported.

    A check answering a threshold writes the number it measured inside its own message, so driving
    the threshold to zero and reading that number back makes clang-tidy an oracle for a measurement
    the way Pylint's design messages are.
    """

    tool = "clang-tidy magnitude"
    magnitude: ClassVar[re.Pattern[str]] = re.compile(r"(\d+) \(threshold")

    def measured(self, found: Diagnostic) -> int:
        """Return the magnitude clang-tidy wrote inside its own message."""
        stated = self.magnitude.search(found.detail)
        return int(stated.group(1)) if stated is not None else 0


class CppcheckOracle(Oracle):
    """Read what Cppcheck reports for a chosen set of its error identifiers, out of its XML report.

    Cppcheck writes its findings to standard error as XML naming the identifier and every location
    a finding spans. The first location is the place it points at and the rest are the supporting
    sites a reader is sent to afterwards, so each of them is one located finding here.
    """

    tool = "cppcheck"
    binary = "cppcheck"

    standard: str = "c++20"

    def diagnostics(self, root: Path) -> list[Diagnostic]:
        """Return every finding one of the chosen identifiers produced over one tree."""
        completed = self.ran(
            [
                "cppcheck",
                "--enable=all",
                "--inline-suppr",
                "--quiet",
                "--xml",
                f"--std={self.standard}",
                str(root),
            ]
        )
        wanted = set(self.rules)
        return [
            Diagnostic(
                path=str(root / found.attrib["file"]),
                line=int(found.attrib["line"]),
                rule=error.attrib["id"],
                detail=error.attrib.get("msg", ""),
            )
            for error in ElementTree.fromstring(completed.stderr).iter("error")
            if error.attrib.get("id") in wanted
            for found in error.iter("location")
            if "file" in found.attrib
        ]


def scalar_row(row: Mapping[str, RuleValue | None]) -> RuleValue:
    """Return the one populated scalar column from a normalized value row."""
    for name in ("boolean_value", "integer_value", "float_value", "category_value"):
        if (value := row[name]) is not None:
            return value
    raise TypeError("the rule emitted no scalar value")


def required_row_value[Value: RuleValue](
    row: Mapping[str, RuleValue | None], name: str, expected: type[Value]
) -> Value:
    """Return one required Polars row value after checking its declared scalar type."""
    value = row[name]
    if not isinstance(value, expected):
        raise TypeError(f"{name} must contain {expected.__name__}")
    return value
