import json
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ElementTree
from abc import ABC, abstractmethod
from collections import Counter
from enum import StrEnum, auto
from functools import cache
from importlib.util import find_spec
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, NamedTuple, Protocol

import pytest
from hypothesis import strategies as st

from mcmr.bases import FrozenFlexModel
from mcmr.catalog import Catalog
from mcmr.discovery import RuleModuleDiscovery
from mcmr.facts import Fact
from mcmr.kernel import Kernel, locate
from mcmr.models import RuleAnswer, RuleContract, RuleSetting, answered, explained
from tests.conftest import synchronous

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

ROOT = Path(__file__).parents[1]
BINARY = locate(ROOT)


class Site(NamedTuple):
    """One located finding, as a path relative to the tree and the lines it covers.

    The path is relative to the tree rather than a base name, because a real checkout holds a dozen
    files called `__init__.py` and a one-file fixture folds every reader onto one name whatever
    either of them answered. A point finding covers one line and a rule reading a whole declaration
    covers its range, which is what lets two readers pinned at different granularities be compared
    without either being widened to meet the other.
    """

    path: str
    line: int
    through: int

    @classmethod
    def at(cls, path: str, line: int) -> Site:
        """Return the site one reader named by a single line."""
        return cls(path=path, line=line, through=line)

    @property
    def width(self) -> int:
        """Return how many lines this site covers."""
        return self.through - self.line + 1

    def holds(self, other: Site) -> bool:
        """Whether this site covers the whole of another one in the same file."""
        return (
            self.path == other.path and self.line <= other.line and other.through <= self.through
        )


class Report(FrozenFlexModel):
    """Every finding one reader stated over one tree, as a multiset of located sites.

    A multiset rather than a set, because two findings on one line are two findings and a reader
    that states one of them has not agreed. Nothing here exposes a total, so a comparison cannot be
    written against a count, which is the weak form this whole harness exists to make hard.
    """

    reader: str
    sites: tuple[Site, ...] = ()

    @property
    def tally(self) -> Counter[Site]:
        """Return how many findings this reader stated at each site."""
        return Counter(self.sites)

    def states(self, *sites: Site) -> bool:
        """Whether this reader stated exactly these findings and no others.

        This is how a fixture pins what an oracle answers about it, so a comparison that passed
        because both readers went quiet fails here first.
        """
        return self.tally == Counter(sites)

    def plus(self, *sites: Site) -> Report:
        """Return this report widened by findings the other reader is documented to state too.

        A divergence written out in full stays an equality, which is a great deal stronger than
        replacing it with a containment that any silent reader satisfies.
        """
        return Report(reader=self.reader, sites=(*self.sites, *sites))

    def minus(self, *sites: Site) -> Report:
        """Return this report without findings the other reader is documented not to state."""
        remaining = self.tally - Counter(sites)
        if sum(remaining.values()) + len(sites) != len(self.sites):
            raise ValueError(f"{self.reader} never stated {sorted(set(sites) - set(self.sites))}")
        return Report(reader=self.reader, sites=tuple(remaining.elements()))

    def narrowed_to(self, other: Report) -> Report:
        """Return these sites folded onto the ranges another reader states around them.

        Each reader pins a finding as precisely as its evidence allows, so Pylint names a line
        where a rule reading one declaration answers for the whole of it. Folding the finer side
        into the coarser one's ranges is what makes the two comparable, and the narrowest range
        wins so a finding in the wrong callable stays in the wrong callable rather than being
        absorbed by the class around it. A site no range holds is left where it is, so a
        disagreement stays visible instead of being swallowed.
        """
        ranges = sorted(
            {site for site in other.sites if site.width > 1}, key=lambda site: site.width
        )
        return Report(
            reader=self.reader, sites=tuple(self.folded(ranges, site) for site in self.sites)
        )

    def folded(self, ranges: Sequence[Site], site: Site) -> Site:
        """Return the narrowest range holding one point, or the site itself when none does."""
        if site.width > 1:
            return site
        return next((held for held in ranges if held.holds(site)), site)


class Relation(StrEnum):
    """Say how what MCMR reported stands to what an upstream tool reported.

    MCMR is deliberately wider than an oracle in some places and narrower in others, and stating
    which is what keeps a difference visible instead of tuned away. An equality compares the two
    multisets, so a reader that found the same place twice as often has not agreed. A containment
    compares the distinct places instead, since a rule pinned to a declaration states one finding
    where a line-pinned reader states several and multiplicity is not a claim either can make about
    the other. A disjoint pair demands that both readers actually spoke, so it can never pass
    because one of them was silent. A union is where one MCMR rule answers what several upstream
    rules answer between them, and each of those is named rather than merged behind one selection.
    """

    EQUALS = auto()
    SUBSET = auto()
    SUPERSET = auto()
    DISJOINT = auto()
    UNION = auto()

    def stated_between(self, tools: int) -> bool:
        """Whether this relation can be stated between MCMR and that many upstream rules."""
        return tools >= 2 if self is Relation.UNION else tools == 1


class Comparison(FrozenFlexModel):
    """One stated relation between what MCMR reported and what its oracles reported.

    The reason travels with the relation, because a difference nobody wrote down is a difference
    somebody will later delete. Every comparison carries one, and a comparison whose two sides
    disagree prints both halves rather than a Boolean.
    """

    ours: Report
    theirs: tuple[Report, ...]
    relation: Relation
    reason: str

    @property
    def upstream(self) -> Report:
        """Return what the oracle side states, counting a finding two rules share only once."""
        merged: Counter[Site] = Counter()
        for report in self.theirs:
            merged |= report.tally
        return Report(
            reader=" and ".join(report.reader for report in self.theirs),
            sites=tuple(merged.elements()),
        )

    def aligned(self) -> tuple[Counter[Site], Counter[Site]]:
        """Return both sides expressed in each other's ranges, ready to be compared."""
        theirs = self.upstream
        return self.ours.narrowed_to(theirs).tally, theirs.narrowed_to(self.ours).tally

    def holds(self) -> bool:
        """Whether the stated relation is what the two readers actually said."""
        ours, theirs = self.aligned()
        match self.relation:
            case Relation.EQUALS | Relation.UNION:
                return ours == theirs
            case Relation.SUBSET:
                return set(ours) <= set(theirs)
            case Relation.SUPERSET:
                return set(ours) >= set(theirs)
            case _:
                return bool(ours) and bool(theirs) and not set(ours) & set(theirs)

    def explain(self) -> str:
        """Return the whole disagreement, both readers named and every unshared site on each."""
        ours, theirs = self.aligned()
        return "\n".join(
            [
                f"{self.ours.reader} {self.relation} {self.upstream.reader} fails: {self.reason}",
                f"  only {self.ours.reader}: {sorted((ours - theirs).elements())}",
                f"  only {self.upstream.reader}: {sorted((theirs - ours).elements())}",
            ]
        )


def differ(ours: Report, relation: Relation, *theirs: Report, because: str) -> None:
    """Assert one stated relation between an MCMR rule and the oracles it is compared against.

    `because` is required, so an equality can never be written without saying why it is one and a
    containment can never be written without saying which side is deliberately the wider reader.
    """
    if not relation.stated_between(len(theirs)):
        raise ValueError(f"{relation} cannot be stated between MCMR and {len(theirs)} tools")
    comparison = Comparison(ours=ours, theirs=theirs, relation=relation, reason=because)
    assert comparison.holds(), comparison.explain()


class Reader(Protocol):
    """State where one analysis found something over one tree.

    Both halves of a comparison satisfy this, which is what lets one relation be asserted between
    an MCMR rule and an upstream tool without either side learning what the other is.
    """

    @property
    def name(self) -> str:
        """Return what this reader is called in a failure message."""
        ...

    def report(self, root: Path) -> Report:
        """Return every finding this reader states over one tree."""
        ...


class Diagnostic(FrozenFlexModel):
    """One finding an upstream tool reported, in the shape every adapter reduces its output to."""

    path: str
    line: int
    rule: str = ""
    detail: str = ""


class Oracle(FrozenFlexModel, ABC):
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

    rules: tuple[str, ...] = ()

    def __init_subclass__(cls) -> None:
        """Register one adapter under the tool it runs."""
        super().__init_subclass__()
        Oracle.oracles[cls.tool] = cls

    @classmethod
    def of(cls, tool: str, *rules: str) -> Oracle:
        """Return the adapter for one tool, asking it for exactly these rules."""
        return cls.oracles[tool](rules=rules)

    @classmethod
    def installed(cls, tool: str) -> bool:
        """Whether the program one registered tool needs can be found here."""
        return cls.oracles[tool].present()

    @classmethod
    def present(cls) -> bool:
        """Whether this tool's program is on the path."""
        return shutil.which(cls.binary) is not None

    @property
    def name(self) -> str:
        """Return the tool and the rules this adapter asked it for."""
        return " ".join((self.tool, *self.rules))

    def report(self, root: Path) -> Report:
        """Return where this tool reported over one tree."""
        return Report(
            reader=self.name,
            sites=tuple(
                self.located(root, found.path, found.line)
                for found in self.diagnostics(root)
                for _ in range(self.measured(found))
            ),
        )

    def measured(self, found: Diagnostic) -> int:
        """Return how many findings one diagnostic stands for, which is one for a plain report.

        A tool asked for a magnitude states it once and names the number inside its own message, so
        an adapter reading measurements overrides this and every unit becomes one site. That is
        what makes a measurement compare as a multiset, where a reader measuring eleven against
        twelve would otherwise agree by having reported in the same place.
        """
        return 1

    @abstractmethod
    def diagnostics(self, root: Path) -> list[Diagnostic]:
        """Return every finding this tool reported, read out of its own output."""

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

    def located(self, root: Path, path: str, line: int) -> Site:
        """Return one reported location as a path relative to the tree, since a name is not one."""
        return Site.at(Path(path).resolve().relative_to(root.resolve()).as_posix(), line)


class PylintOracle(Oracle):
    """Read what Pylint reports for a chosen set of its messages, out of its own JSON report."""

    tool = "pylint"
    binary = "pylint"

    options: tuple[str, ...] = ()

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


@cache
def catalog() -> Catalog:
    """Return the whole rule catalog, built once for every comparison in the suite.

    Discovery and validation cost about as much as one kernel run and every oracle case needs one
    rule out of the same catalog, so building it once is the difference between a suite that spawns
    subprocesses and one that also rebuilds the catalog beside every one of them.
    """
    return Catalog(modules=RuleModuleDiscovery().modules)


@cache
def contract(rule_id: str) -> RuleContract:
    """Return the callable one rule identifier names, through the catalog that validates it."""
    built = catalog()
    definition = next(item for item in built.definitions if item.id == rule_id)
    return next(item for item in built.rules if item.callable_path == definition.callable)


@cache
def extracted(root: Path, family: type[Fact], suffixes: tuple[str, ...]) -> tuple[Fact, ...]:
    """Return one fact family the real kernel builds over one tree.

    Cached by the tree it read, since several comparisons ask the same family of the same generated
    project and a kernel run is a process spawn. A tree written to after it has been read once
    would answer from the first reading, so every fixture here writes its whole tree before anyone
    asks anything about it.
    """
    workspace = Kernel(binary=BINARY, root=root, suffixes=suffixes).build(
        [family.__name__], {family.__name__: family}
    )
    return tuple(workspace.streams.get(family, []))


class RuleReader(FrozenFlexModel, ABC):
    """Run one MCMR rule over one tree through the real kernel and say where it answered.

    A rule locates a finding as precisely as the fact it read allows, and that is a property of the
    rule rather than of the comparison, so each subclass is one of the three answers a rule can
    give. Nothing here reads a rule's condition a second time: the rule is always the judge and a
    reader only asks it and records where it spoke.
    """

    rule_id: str
    family: type[Fact]
    settings: dict[str, RuleSetting] = {}
    languages: tuple[str, ...] = ()
    suffixes: tuple[str, ...] = ()

    @property
    def name(self) -> str:
        """Return the rule this reader runs."""
        return self.rule_id

    def report(self, root: Path) -> Report:
        """Return where this rule reported over one tree."""
        return Report(reader=self.name, sites=tuple(self.sites(root)))

    def facts(self, root: Path) -> tuple[Fact, ...]:
        """Return the family this rule reads, narrowed to the languages the case asked for."""
        stream = extracted(root, self.family, self.suffixes)
        if not self.languages:
            return stream
        return tuple(fact for fact in stream if fact.language in self.languages)

    def counted(self, subject: Fact) -> int:
        """Return how many findings the rule answered with about one fact."""
        value = answered(self.invoked(subject))
        return int(value) if isinstance(value, bool | int) else 0

    def stated(self, subject: Fact) -> tuple[Site, ...]:
        """Return the span of every finding the rule stated about one fact."""
        return tuple(
            Site(
                path=finding.span.path,
                line=finding.span.start_line,
                through=finding.span.end_line,
            )
            for finding in explained(self.invoked(subject))
        )

    def invoked(self, subject: Fact) -> RuleAnswer:
        """Return what the rule answered about one fact, refusing an asynchronous lane."""
        return synchronous(
            contract(self.rule_id).invoke(subject, settings=self.settings, dependencies={})
        )

    @abstractmethod
    def sites(self, root: Path) -> Iterable[Site]:
        """Return every site this rule reported over one tree."""


class DeclarationReader(RuleReader):
    """Locate every finding at the declaration the rule answered about, once per unit it counted.

    A rule reading one declaration answers for the whole of it, so the declaration is the finest
    place a count can be pinned to and the count is how many findings sit inside it. Repeating the
    range gives a multiset an oracle's lines fold into, so a rule counting three findings in a
    callable that holds one of them fails even where the totals agree.
    """

    def sites(self, root: Path) -> Iterable[Site]:
        """Return one site per finding, at the range of the declaration that holds it."""
        return [
            Site(path=fact.span.path, line=fact.span.start_line, through=fact.span.end_line)
            for fact in self.facts(root)
            for _ in range(self.counted(fact))
        ]


class MeasureReader(RuleReader):
    """Locate a measurement at the declaration it measures, once per unit of the magnitude.

    A measurement is a property of the declaration rather than a total over the facts that state
    it, so where a family emits one fact per relationship a declaration takes part in, the
    magnitude is the greatest any of them answered rather than their sum. Two `OverrideFact`
    records about one derived class both state that it has two ancestors, and adding them would
    report four.
    """

    def sites(self, root: Path) -> Iterable[Site]:
        """Return one site per unit of the greatest magnitude measured at each declaration."""
        greatest: dict[Site, int] = {}
        for fact in self.facts(root):
            where = Site(
                path=fact.span.path, line=fact.span.start_line, through=fact.span.end_line
            )
            greatest[where] = max(greatest.get(where, 0), self.counted(fact))
        return [where for where, magnitude in greatest.items() for _ in range(magnitude)]


class FindingReader(RuleReader):
    """Locate every finding where the rule itself said it is.

    A rule that has migrated to reporting findings states a span for each one, which is the most
    precise answer available and needs no second reading of anything.
    """

    def sites(self, root: Path) -> Iterable[Site]:
        """Return the span of every finding the rule stated."""
        return [site for fact in self.facts(root) for site in self.stated(fact)]


class RecordReader(RuleReader):
    """Locate every finding at the record inside a fact that caused it.

    A fact carries every record one file states and the rule answers with one number for all of
    them, so comparing against a reader that names a line needs the rule asked again for each
    record alone. The rule stays the judge, which is what makes this a comparison of findings
    rather than a restatement of the rule's condition beside it.
    """

    field: str

    def sites(self, root: Path) -> Iterable[Site]:
        """Return the node of every record the rule reported when it was handed that record."""
        return [
            Site.at(fact.span.path, record.node.span.start_line)
            for fact in self.facts(root)
            for record in getattr(fact, self.field)
            if self.counted(fact.model_copy(update={self.field: [record]}))
            and record.node is not None
        ]


class Shape(NamedTuple):
    """One source shape and which of its own lines a reader is expected to keep reporting.

    The answer travels with the shape rather than being read back out of the source afterwards, so
    a property built from these states an opinion of its own instead of only comparing two readers
    of the same text. `opening` holds what has to stay at the top of a file, such as an import or
    an include, and `body` holds the rest. `reported` indexes into the two concatenated, so a shape
    states its answer wherever the answer sits.
    """

    opening: tuple[str, ...] = ()
    body: tuple[str, ...] = ()
    reported: frozenset[int] = frozenset()


class Source(NamedTuple):
    """One generated source and the lines a reader is expected to report in it."""

    text: str
    reported: frozenset[int]


def placed(shape: Shape, offset: int, opening: int, body: int) -> int:
    """Return the line one of a shape's own lines landed on once a source was assembled."""
    if offset < len(shape.opening):
        return opening + offset
    return body + offset - len(shape.opening)


@st.composite
def assembled(
    draw: st.DrawFn,
    shapes: tuple[Shape, ...],
    *,
    prologue: tuple[str, ...] = (),
    limit: int = 6,
) -> Source:
    """Build one source out of independent shapes and state which of its lines stay reported.

    Every shape names its own declarations, so any subset of them concatenates into a source that
    still says what each of them means. The openings gather at the top in the order they were drawn
    and the bodies follow, which is what a language demanding its imports first requires and what
    every other language tolerates.
    """
    drawn = draw(st.lists(st.sampled_from(shapes), min_size=1, max_size=limit, unique=True))
    opening = list(prologue)
    openings: list[int] = []
    for shape in drawn:
        openings.append(len(opening) + 1)
        opening.extend(shape.opening)
    body: list[str] = []
    bodies: list[int] = []
    for shape in drawn:
        body.extend(("", ""))
        bodies.append(len(opening) + len(body) + 1)
        body.extend(shape.body)
    return Source(
        text="\n".join([*opening, *body, ""]),
        reported=frozenset(
            placed(shape, offset, openings[index], bodies[index])
            for index, shape in enumerate(drawn)
            for offset in shape.reported
        ),
    )


class Trees(FrozenFlexModel):
    """Write one fresh tree per generated example, under a directory pytest cleans up.

    A reading is cached by the tree it read, so a property that draws a new source has to write it
    somewhere nothing has been asked about yet. The number of trees already grown is read off the
    filesystem rather than counted, which keeps this frozen and keeps two properties sharing one
    directory from handing out the same name.
    """

    root: Path

    def grow(self, sources: Mapping[str, str]) -> Path:
        """Write one more generated tree and return it."""
        planted = self.root / f"tree{sum(1 for _ in self.root.iterdir())}"
        planted.mkdir()
        return written(planted, sources)


def written(root: Path, sources: Mapping[str, str]) -> Path:
    """Write one generated source per relative name and return the tree holding them."""
    for relative, source in sources.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
    return root


needs_kernel = pytest.mark.skipif(
    not BINARY.exists(),
    reason="a differential oracle needs the kernel binary this checkout builds",
)


def needs(*tools: str) -> pytest.MarkDecorator:
    """Skip a case whose oracle is not installed here, naming which tool is missing.

    A skipped oracle proves nothing, so the reason names the tool rather than the case, and the
    suite's own summary is then the ledger of what could not be checked on this machine.
    """
    absent = sorted(tool for tool in tools if not Oracle.installed(tool))
    return pytest.mark.skipif(
        bool(absent), reason=f"the differential oracle needs {', '.join(absent)} installed"
    )
