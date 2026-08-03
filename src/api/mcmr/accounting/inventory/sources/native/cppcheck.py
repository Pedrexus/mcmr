import xml.etree.ElementTree as ElementTree

from ...contracts import ToolRule
from ..base import CommandInventory


class CppcheckRegistry(CommandInventory):
    """Read Cppcheck identifiers from its XML error list."""

    tool = "cppcheck"
    listing = ("cppcheck", "--errorlist")

    def rules(self, listed: str) -> list[ToolRule]:
        """Return every error identifier grouped by its severity."""
        stated = {
            error.attrib["id"]: error.attrib.get("severity", "")
            for error in ElementTree.fromstring(listed).iter("error")
        }
        return [ToolRule(symbol=name, group=stated[name]) for name in sorted(stated)]

    def version(self, spoken: str) -> str:
        """Return the release Cppcheck states in its error list header."""
        found = ElementTree.fromstring(spoken).find("cppcheck")
        if found is None:
            raise ValueError("cppcheck printed no version element")
        return found.attrib["version"]
