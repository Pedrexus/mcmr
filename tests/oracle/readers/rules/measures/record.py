from pathlib import Path
from typing import TYPE_CHECKING

from ....contracts import Site

if TYPE_CHECKING:
    from collections.abc import Iterable

from ..base import RuleReader


class RecordReader(RuleReader):
    """Locate every finding at the record inside a fact that caused it.

    A fact carries every record one file states and the rule answers with one number for all of
    them, so comparing against a reader that names a line needs the rule asked again for each
    record alone. The rule stays the judge, which is what makes this a comparison of findings
    rather than a restatement of the rule's condition beside it.
    """

    field: str

    def sites(self, root: Path) -> Iterable[Site]:
        """Return the node of every record the rule reported when it was handed that record."""
        return [
            Site.at(fact.span.path, record.node.span.start_line)
            for fact in self.facts(root)
            for record in getattr(fact, self.field)
            if self.counted(fact.model_copy(update={self.field: [record]}))
            and record.node is not None
        ]
