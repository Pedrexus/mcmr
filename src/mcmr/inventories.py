import json
import re
import shutil
import subprocess
import xml.etree.ElementTree as ElementTree
from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar, Protocol

from pylint import __version__ as pylint_version
from pylint.lint import PyLinter

from .bases import FrozenFlexModel
from .upstream import Inventory, ToolRule


class InventorySource(Protocol):
    """Read one tool's own rule registry, so a frozen inventory is never hand-written.

    Every source asks the tool itself rather than a remembered list, which is what makes a rule the
    tool renamed or retired turn a reference red instead of leaving it standing.
    """

    def read(self) -> Inventory:
        """Return every rule the installed tool ships today."""
        ...


class PylintRegistry(FrozenFlexModel):
    """Read Pylint's message store through its own linter, with the default plugins loaded."""

    def read(self) -> Inventory:
        """Return every message Pylint emits, with the checker that owns it."""
        linter = PyLinter()
        linter.load_default_plugins()
        emitted = {
            ToolRule(code=message.msgid, symbol=message.symbol, group=message.checker_name)
            for message in linter.msgs_store.messages
        }
        ordered = sorted(emitted, key=lambda message: message.code)
        return Inventory(tool="pylint", version=pylint_version, rules=tuple(ordered))


class CommandInventory(FrozenFlexModel, ABC):
    """Read one tool's registry by running that tool and reading what it prints.

    Every tool but Pylint answers from outside the interpreter, and each of them answers
    differently: Ruff prints JSON, Clippy prints two aligned tables, clang-tidy prints one name per
    line, Cppcheck prints XML, and ESLint prints nothing at all until a Node process asks its own
    module for the map it exports. What they share is the shape of the work, so running the command
    lives here once and each subclass only says which command and how to read the answer.

    Naming the command apart from the parsing is what keeps this checkable on a machine that cannot
    install every tool. The parsing is held to an answer captured from the tool, and the whole
    reading is held to the tool itself wherever it is present.
    """

    tool: ClassVar[str]
    listing: ClassVar[tuple[str, ...]]
    release: ClassVar[tuple[str, ...]] = ()

    def read(self) -> Inventory:
        """Return every rule the installed tool ships, asked of the tool itself."""
        listed = self.spoken(self.listing)
        return Inventory(
            tool=self.tool,
            version=self.version(self.spoken(self.release) if self.release else listed),
            rules=self.rules(listed),
        )

    def spoken(self, command: tuple[str, ...]) -> str:
        """Run one command and return what it printed, refusing a tool that failed to answer.

        Standard input is closed with an empty string because `clippy-driver` reads a source from
        it and would otherwise wait forever, and no other listing reads anything.
        """
        answered = subprocess.run(
            list(command),
            input="",
            capture_output=True,
            text=True,
            check=True,
            cwd=self.directory(),
        )
        return answered.stdout

    def directory(self) -> Path | None:
        """Return where this listing has to run, which is nowhere in particular for most tools."""
        return None

    @abstractmethod
    def version(self, spoken: str) -> str:
        """Return the release this tool says it is."""

    @abstractmethod
    def rules(self, listed: str) -> tuple[ToolRule, ...]:
        """Return every rule the printed listing names, in a stable order."""


class RuffRegistry(CommandInventory):
    """Read Ruff's rule table out of `ruff rule --all`, which prints it as JSON."""

    tool = "ruff"
    listing = ("ruff", "rule", "--all", "--output-format", "json")
    release = ("ruff", "--version")

    def version(self, spoken: str) -> str:
        """Return the release from the one line `ruff --version` prints."""
        return spoken.split()[-1]

    def rules(self, listed: str) -> tuple[ToolRule, ...]:
        """Return every rule Ruff ships, grouped by the linter it took the rule from."""
        shipped = [
            ToolRule(code=rule["code"], symbol=rule["name"], group=rule["linter"])
            for rule in json.loads(listed)
        ]
        return tuple(sorted(shipped, key=lambda rule: rule.code))


class ClippyRegistry(CommandInventory):
    """Read Clippy's lint table out of `clippy-driver -W help`, which prints it as text.

    The driver answers on an empty source, so the listing costs no compilation. It prints lints and
    lint groups in separate tables, and the group a lint belongs to is only in the second, so the
    two are read together and `clippy::all` is skipped because it is every other group at once.
    """

    tool = "clippy"
    listing = ("clippy-driver", "-W", "help", "-")
    release = ("clippy-driver", "--version")

    row: ClassVar[re.Pattern[str]] = re.compile(r"\s{2,}(clippy::\S+)\s{2,}(\S.*?)\s*")
    heading: ClassVar[re.Pattern[str]] = re.compile(
        r"^Lint (checks|groups) (?:provided|loaded) by [^\n]*:$", re.MULTILINE
    )

    def version(self, spoken: str) -> str:
        """Return the release from the line `clippy-driver --version` prints."""
        return spoken.split()[1]

    def rules(self, listed: str) -> tuple[ToolRule, ...]:
        """Return every lint Clippy ships, with the group that carries it."""
        tables = self.heading.split(listed)
        lints: list[str] = []
        groups: dict[str, str] = {}
        for kind, table in zip(tables[1::2], tables[2::2], strict=True):
            for name, rest in self.rows(table):
                if kind == "checks":
                    lints.append(name)
                    continue
                for member in self.members(rest) if name != "all" else ():
                    groups.setdefault(member, name)
        return tuple(ToolRule(symbol=lint, group=groups.get(lint, "")) for lint in sorted(lints))

    def rows(self, table: str) -> list[tuple[str, str]]:
        """Return the name and the rest of every Clippy row of one printed table."""
        return [
            (match.group(1).removeprefix("clippy::").replace("-", "_"), match.group(2))
            for line in table.splitlines()
            if (match := self.row.fullmatch(line)) is not None
        ]

    def members(self, listing: str) -> list[str]:
        """Return the lints one printed group row names, which is a comma-separated list."""
        return [
            member.strip().removeprefix("clippy::").replace("-", "_")
            for member in listing.split(",")
        ]


# What a Node process has to do to hand back an ESLint registry. `eslint --print-config` prints a
# configuration rather than a registry, and the only listing of what a plugin ships is the map the
# package exports, so the inventory is one script rather than one flag. Both maps are read the same
# way and both halves are written under the plain name, since that is the identity the rule's own
# documentation uses and the only one a reference line can spell, where a configuration writes the
# plugin half behind an `@typescript-eslint/` prefix. Each package states its own
# release, ESLint on its own class and the plugin in the metadata every ESLint plugin declares, so
# nothing here has to open a manifest. Resolution runs from the working directory, which is where a
# project keeps the installation being inventoried.
ESLINT_SCRIPT = """
const listed = (rules) =>
  [...rules].map(([name, rule]) => ({
    symbol: name,
    group: rule.meta && rule.meta.deprecated ? "deprecated" : (rule.meta || {}).type || "",
  }));
const { ESLint } = await import("eslint");
const { builtinRules } = await import("eslint/use-at-your-own-risk");
const loaded = await import("typescript-eslint");
const plugin = (loaded.default || loaded).plugin;
console.log(
  JSON.stringify({
    eslint: { version: ESLint.version, rules: listed(builtinRules.entries()) },
    "typescript-eslint": {
      version: (plugin.meta || {}).version || "",
      rules: listed(Object.entries(plugin.rules || {})),
    },
  }),
);
"""


class NodeRegistry(CommandInventory):
    """Read one ESLint registry out of the map its own package exports.

    ESLint has no flag that prints what it ships, so the listing is a Node process importing the
    package and handing back both registries at once. One run answers for the core rules and for
    the TypeScript plugin, and each subclass takes the half it is the inventory of.
    """

    listing = ("node", "--input-type=module", "-e", ESLINT_SCRIPT)

    def directory(self) -> Path | None:
        """Return the project the installed ESLint sits in, since Node resolves from the process.

        A bare specifier is looked up in the `node_modules` chain above the directory the process
        runs in, so a listing run anywhere else finds nothing whatever is installed. Walking up
        from the binary on the path is what a project's own tooling already does.
        """
        found = shutil.which("eslint")
        if found is None:
            raise FileNotFoundError("eslint is not installed")
        packages = next(
            (parent for parent in Path(found).resolve().parents if parent.name == "node_modules"),
            None,
        )
        if packages is None:
            raise FileNotFoundError(f"{found} sits outside any node_modules directory")
        return packages.parent

    def version(self, spoken: str) -> str:
        """Return the release the package this inventory is for says it is."""
        return str(json.loads(spoken)[self.tool]["version"])

    def rules(self, listed: str) -> tuple[ToolRule, ...]:
        """Return every rule this package ships, by the name a configuration enables it with.

        A rule's group is the kind its own metadata declares, which is what lets a gap answer for
        every layout rule at once, and a rule the package has retired is grouped as deprecated
        instead, since a retired rule is not a gap in anybody's coverage.
        """
        shipped = [
            ToolRule(symbol=rule["symbol"], group=rule["group"])
            for rule in json.loads(listed)[self.tool]["rules"]
        ]
        return tuple(sorted(shipped, key=lambda rule: rule.symbol))


class ESLintRegistry(NodeRegistry):
    """Read the rules ESLint itself ships, which is `builtinRules` and nothing else."""

    tool = "eslint"


class TypeScriptESLintRegistry(NodeRegistry):
    """Read the rules the typescript-eslint plugin ships, under the prefix a config spells."""

    tool = "typescript-eslint"


class ClangTidyRegistry(CommandInventory):
    """Read clang-tidy's checks out of `--list-checks`, which prints one name per line.

    Every check is enabled first, because the flag lists what is enabled rather than what exists,
    and a default run enables a fraction of them. The module a check belongs to is the part of its
    name before the first hyphen, which is how the project groups them and how a gap can answer for
    a whole module at once.
    """

    tool = "clang-tidy"
    listing = ("clang-tidy", "--list-checks", "-checks=*")
    release = ("clang-tidy", "--version")

    stated: ClassVar[re.Pattern[str]] = re.compile(r"LLVM version (\S+)")

    def version(self, spoken: str) -> str:
        """Return the LLVM release clang-tidy prints inside its own banner."""
        found = self.stated.search(spoken)
        if found is None:
            raise ValueError("clang-tidy printed no LLVM version")
        return found.group(1)

    def rules(self, listed: str) -> tuple[ToolRule, ...]:
        """Return every check the tool enables, with the module its name opens on."""
        named = sorted(
            {
                stripped
                for line in listed.splitlines()[1:]
                if (stripped := line.strip()) and "-" in stripped
            }
        )
        return tuple(ToolRule(symbol=check, group=check.split("-", 1)[0]) for check in named)


class CppcheckRegistry(CommandInventory):
    """Read Cppcheck's identifiers out of `--errorlist`, which prints them as XML.

    The document carries the release beside the errors, so one call answers both questions. Every
    error states the severity it is reported at, which is the only grouping Cppcheck has and the
    one a project turns on and off with `--enable`.
    """

    tool = "cppcheck"
    listing = ("cppcheck", "--errorlist")

    def version(self, spoken: str) -> str:
        """Return the release Cppcheck states in the header of its own error list."""
        found = ElementTree.fromstring(spoken).find("cppcheck")
        if found is None:
            raise ValueError("cppcheck printed no version element")
        return found.attrib["version"]

    def rules(self, listed: str) -> tuple[ToolRule, ...]:
        """Return every error identifier Cppcheck can report, grouped by its severity."""
        stated = {
            error.attrib["id"]: error.attrib.get("severity", "")
            for error in ElementTree.fromstring(listed).iter("error")
        }
        return tuple(ToolRule(symbol=name, group=stated[name]) for name in sorted(stated))


class FrozenInventories(FrozenFlexModel):
    """Regenerate the inventories this package ships, one file per tool.

    `mcmr.data` holds what each tool shipped on the day it was read, so a coverage report is
    reproducible without every tool installed. Rewriting a file is a maintenance step, and the
    suite compares the frozen copy against the installed tool wherever that tool is present.
    """

    sources: ClassVar[dict[str, InventorySource]] = {
        "pylint": PylintRegistry(),
        "ruff": RuffRegistry(),
        "clippy": ClippyRegistry(),
        "eslint": ESLintRegistry(),
        "typescript-eslint": TypeScriptESLintRegistry(),
        "clang-tidy": ClangTidyRegistry(),
        "cppcheck": CppcheckRegistry(),
    }

    def read(self, tool: str) -> Inventory:
        """Return what the installed copy of one tool ships today."""
        return self.sources[tool].read()

    def write(self, tool: str, directory: Path) -> Path:
        """Freeze one tool's inventory into the data directory and return the file written."""
        path = directory / f"{tool}.json"
        listing = self.read(tool).model_dump(exclude_defaults=True)
        path.write_text(json.dumps(listing, indent=1, sort_keys=True) + "\n")
        return path
