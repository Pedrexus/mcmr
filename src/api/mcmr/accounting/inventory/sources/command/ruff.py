import json

from ...contracts import ToolRule
from ..base import CommandInventory


class RuffRegistry(CommandInventory):
    """Read Ruff's rule table out of `ruff rule --all`."""

    tool = "ruff"
    listing = ("ruff", "rule", "--all", "--output-format", "json")
    release = ("ruff", "--version")

    def rules(self, listed: str) -> list[ToolRule]:
        """Return every rule Ruff ships, grouped by its source linter."""
        shipped = [
            ToolRule(code=rule["code"], symbol=rule["name"], group=rule["linter"])
            for rule in json.loads(listed)
        ]
        return sorted(shipped, key=lambda rule: rule.code)

    def version(self, spoken: str) -> str:
        """Return the release from the one line `ruff --version` prints."""
        return spoken.split()[-1]
