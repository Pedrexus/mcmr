import json
import shutil
import subprocess
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

from patos import Registry

from ..contracts import Inventory, ToolRule

if TYPE_CHECKING:
    from typing import ClassVar

_ESLINT_SCRIPT = """
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


class _InventorySources:
    """Own the common contracts used by every live inventory source."""

    class Source(Registry, ABC):
        """Read one tool's registry so a frozen inventory is never hand-written."""

        @abstractmethod
        def read(self) -> Inventory:
            """Return every rule the installed tool ships today."""

    class Command(Source):
        """Read one external tool registry from the command that owns it."""

        tool: ClassVar[str]
        listing: ClassVar[tuple[str, ...]]
        release: ClassVar[tuple[str, ...]] = ()

        @staticmethod
        def rule(*, symbol: str, group: str) -> ToolRule:
            """Build one normalized upstream tool rule."""
            return ToolRule(symbol=symbol, group=group)

        def directory(self) -> Path | None:
            """Return where this listing runs, which most tools do not constrain."""
            return None

        def read(self) -> Inventory:
            """Return every rule the installed tool ships, asked of the tool itself."""
            listed = self.spoken(self.listing)
            release = self.spoken(self.release) if self.release else listed
            return Inventory(
                tool=self.tool,
                version=self.version(release),
                rules=self.rules(listed),
            )

        @abstractmethod
        def rules(self, listed: str) -> list[ToolRule]:
            """Return every rule the printed listing names, in a stable order."""

        def spoken(self, command: tuple[str, ...]) -> str:
            """Run one command and return what it printed, refusing a failed answer."""
            answered = subprocess.run(
                list(command),
                input="",
                capture_output=True,
                text=True,
                check=True,
                cwd=self.directory(),
            )
            return answered.stdout

        @abstractmethod
        def version(self, spoken: str) -> str:
            """Return the release this tool says it is."""

    class Node(Command):
        """Read one ESLint registry from the map its own package exports."""

        listing = ("node", "--input-type=module", "-e", _ESLINT_SCRIPT)

        def directory(self) -> Path:
            """Return the project holding the installed ESLint package."""
            found = shutil.which("eslint")
            if found is None:
                raise FileNotFoundError("eslint is not installed")
            packages = next(
                (
                    parent
                    for parent in Path(found).resolve().parents
                    if parent.name == "node_modules"
                ),
                None,
            )
            if packages is None:
                raise FileNotFoundError(f"{found} sits outside any node_modules directory")
            return packages.parent

        def rules(self, listed: str) -> list[ToolRule]:
            """Return every rule this package ships under its configuration name."""
            shipped = [
                self.rule(symbol=rule["symbol"], group=rule["group"])
                for rule in json.loads(listed)[self.tool]["rules"]
            ]
            return sorted(shipped, key=lambda rule: rule.symbol)

        def version(self, spoken: str) -> str:
            """Return the release the package this inventory is for says it is."""
            return str(json.loads(spoken)[self.tool]["version"])


CommandInventory = _InventorySources.Command
InventorySource = _InventorySources.Source
NodeRegistry = _InventorySources.Node
