import re
from typing import TYPE_CHECKING

from ...contracts import ToolRule
from ..base import CommandInventory

if TYPE_CHECKING:
    from typing import ClassVar


class ClangTidyRegistry(CommandInventory):
    """Read clang-tidy checks from `--list-checks`."""

    tool = "clang-tidy"
    listing = ("clang-tidy", "--list-checks", "-checks=*")
    release = ("clang-tidy", "--version")
    stated: ClassVar[re.Pattern[str]] = re.compile(r"LLVM version (\S+)")

    def rules(self, listed: str) -> list[ToolRule]:
        """Return every check with the module its name opens on."""
        named = sorted(
            {
                stripped
                for line in listed.splitlines()[1:]
                if (stripped := line.strip()) and "-" in stripped
            }
        )
        return [ToolRule(symbol=check, group=check.split("-", 1)[0]) for check in named]

    def version(self, spoken: str) -> str:
        """Return the LLVM release clang-tidy prints inside its banner."""
        found = self.stated.search(spoken)
        if found is None:
            raise ValueError("clang-tidy printed no LLVM version")
        return found.group(1)
