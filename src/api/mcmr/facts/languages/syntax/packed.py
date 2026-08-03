from functools import cached_property
from typing import TYPE_CHECKING

from ...foundation import SourceSpan, SyntaxElement, SyntaxRecord, SyntaxTraversal

if TYPE_CHECKING:
    from .fact import SyntaxFact


class PackedNode(SyntaxTraversal):
    """Read one compact preorder record without retaining an object tree."""

    def __init__(self, fact: SyntaxFact, index: int) -> None:
        self.fact = fact
        self.index = index

    @property
    def children(self) -> list[SyntaxElement]:
        """Return lightweight views over this node's direct children."""
        return [self.__class__(self.fact, index) for index in self.record[6]]

    @property
    def kind(self) -> str:
        """Return the language-neutral node kind."""
        return self.record[0]

    @property
    def name(self) -> str:
        """Return the name this node states when it states one."""
        return self.record[1]

    @property
    def record(self) -> SyntaxRecord:
        """Return this node's compact wire record."""
        return self.fact.nodes[self.index]

    @cached_property
    def span(self) -> SourceSpan:
        """Locate this node in the source retained by its fact."""
        return SourceSpan(
            path=self.fact.span.path,
            start_line=self.record[2],
            start_column=self.record[3],
            end_line=self.record[4],
            end_column=self.record[5],
        )

    @property
    def text(self) -> str:
        """Leave source ownership with the fact."""
        return ""
