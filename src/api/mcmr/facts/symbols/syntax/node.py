from patos import FrozenModel

from ...foundation import SourceSpan, SyntaxTraversal


class SyntaxNode(SyntaxTraversal, FrozenModel):
    """Retain one declaration tree node and the source it spans."""

    kind: str
    name: str = ""
    text: str = ""
    span: SourceSpan | None = None
    children: list["SyntaxNode"] = []
