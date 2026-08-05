from pathlib import Path
from typing import TYPE_CHECKING

from ....adapters import required_row_value, scalar_row
from ....contracts import Site

if TYPE_CHECKING:
    from collections.abc import Iterable

from ..base import RuleReader


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
        for row in self.values(root):
            where = Site(
                path=required_row_value(row, "path", str),
                line=required_row_value(row, "start_line", int),
                through=required_row_value(row, "end_line", int),
            )
            greatest[where] = max(greatest.get(where, 0), int(scalar_row(row)))
        return [where for where, magnitude in greatest.items() for _ in range(magnitude)]
