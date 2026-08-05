from pathlib import Path
from typing import TYPE_CHECKING

from ...adapters import required_row_value, scalar_row
from ...contracts import Site

if TYPE_CHECKING:
    from collections.abc import Iterable

from .base import RuleReader


class DeclarationReader(RuleReader):
    """Locate every finding at the declaration the rule answered about, once per unit it counted.

    A rule reading one declaration answers for the whole of it, so the declaration is the finest
    place a count can be pinned to and the count is how many findings sit inside it. Repeating the
    range gives a multiset an oracle's lines fold into, so a rule counting three findings in a
    callable that holds one of them fails even where the totals agree.
    """

    def sites(self, root: Path) -> Iterable[Site]:
        """Return one site per finding, at the range of the declaration that holds it."""
        return [
            Site(
                path=required_row_value(row, "path", str),
                line=required_row_value(row, "start_line", int),
                through=required_row_value(row, "end_line", int),
            )
            for row in self.values(root)
            for _ in range(int(scalar_row(row)))
        ]
