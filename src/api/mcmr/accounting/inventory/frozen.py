import json
from typing import TYPE_CHECKING

from .sources import InventorySource

if TYPE_CHECKING:
    from pathlib import Path

    from .contracts import Inventory


class FrozenInventories:
    """Regenerate the frozen inventory this package ships for each upstream tool."""

    def read(self, tool: str) -> Inventory:
        """Return what the installed copy of one tool ships today."""
        return InventorySource.find(tool, attr="tool")().read()

    def write(self, tool: str, directory: Path) -> Path:
        """Freeze one tool inventory into the data directory and return its path."""
        path = directory / f"{tool}.json"
        listing = self.read(tool).model_dump(exclude_defaults=True)
        path.write_text(json.dumps(listing, indent=1, sort_keys=True) + "\n")
        return path
