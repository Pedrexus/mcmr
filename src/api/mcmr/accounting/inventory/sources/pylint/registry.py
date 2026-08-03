from typing import TYPE_CHECKING

from pylint import __version__ as pylint_version
from pylint.lint import PyLinter

from ...contracts import Inventory, ToolRule
from ..base import InventorySource

if TYPE_CHECKING:
    from typing import ClassVar


class PylintRegistry(InventorySource):
    """Read Pylint's message store through its own linter and default plugins."""

    tool: ClassVar[str] = "pylint"

    def read(self) -> Inventory:
        """Return every message Pylint emits, with the checker that owns it."""
        linter = PyLinter()
        linter.load_default_plugins()
        emitted: set[ToolRule] = {
            ToolRule(code=message.msgid, symbol=message.symbol, group=message.checker_name)
            for message in linter.msgs_store.messages
        }
        ordered = sorted(emitted, key=lambda message: message.code)
        return Inventory(tool="pylint", version=pylint_version, rules=ordered)
