import re
from typing import TYPE_CHECKING

from ...contracts import ToolRule
from ..base import CommandInventory

if TYPE_CHECKING:
    from collections.abc import Iterable
    from typing import ClassVar


class ClippyRegistry(CommandInventory):
    """Read Clippy's lint and group tables out of `clippy-driver -W help`."""

    tool = "clippy"
    listing = ("clippy-driver", "-W", "help", "-")
    release = ("clippy-driver", "--version")

    row: ClassVar[re.Pattern[str]] = re.compile(r"\s{2,}(clippy::\S+)\s{2,}(\S.*?)\s*")
    heading: ClassVar[re.Pattern[str]] = re.compile(
        r"^Lint (checks|groups) (?:provided|loaded) by [^\n]*:$", re.MULTILINE
    )

    def members(self, listing: str) -> list[str]:
        """Return the lints one comma-separated group row names."""
        return [
            member.strip().removeprefix("clippy::").replace("-", "_")
            for member in listing.split(",")
        ]

    def rows(self, table: str) -> list[tuple[str, str]]:
        """Return the name and remaining columns of every Clippy table row."""
        return [
            (match.group(1).removeprefix("clippy::").replace("-", "_"), match.group(2))
            for line in table.splitlines()
            if (match := self.row.fullmatch(line)) is not None
        ]

    def rules(self, listed: str) -> list[ToolRule]:
        """Return every lint Clippy ships, with the group that carries it."""
        tables = self.heading.split(listed)
        rows = {
            kind: self.rows(table) for kind, table in zip(tables[1::2], tables[2::2], strict=True)
        }
        lints = [name for name, _ in rows.get("checks", [])]
        groups = self._groups(rows.get("groups", []))
        return [ToolRule(symbol=lint, group=groups.get(lint, "")) for lint in sorted(lints)]

    def version(self, spoken: str) -> str:
        """Return the release from the line `clippy-driver --version` prints."""
        return spoken.split()[1]

    def _groups(self, rows: Iterable[tuple[str, str]]) -> dict[str, str]:
        """Map each lint to the first named group that includes it."""
        groups: dict[str, str] = {}
        for name, listing in rows:
            if name == "all":
                continue
            for member in self.members(listing):
                groups.setdefault(member, name)
        return groups
