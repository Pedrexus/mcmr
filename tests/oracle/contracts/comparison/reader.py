from pathlib import Path
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from ..report import Report


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
