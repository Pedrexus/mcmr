from pathlib import Path
from typing import TYPE_CHECKING

from ...contracts import Site

if TYPE_CHECKING:
    from collections.abc import Iterable

from .base import RuleReader


class FindingReader(RuleReader):
    """Locate every finding where the rule itself said it is.

    A rule that has migrated to reporting findings states a span for each one, which is the most
    precise answer available and needs no second reading of anything.
    """

    def sites(self, root: Path) -> Iterable[Site]:
        """Return the span of every finding the rule stated."""
        query = self.query(root)
        if query.findings is None:
            return []
        allowed = {str(row["fact_id"]) for row in self.narrowed_values(query)}
        return [
            Site(path=row["path"], line=row["start_line"], through=row["end_line"])
            for row in query.findings.rows.collect().iter_rows(named=True)
            if str(row["fact_id"]) in allowed
        ]
