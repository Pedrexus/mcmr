from functools import cached_property
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Iterator

    from .syntax import SyntaxElement


class SyntaxTraversal:
    """Share preorder navigation across expanded and compact syntax nodes."""

    @cached_property
    def depth(self) -> int:
        """Return how deeply this node nests without recursion."""
        deepest = 0
        pending: list[tuple[SyntaxElement, int]] = [(cast("SyntaxElement", self), 1)]
        while pending:
            node, level = pending.pop()
            deepest = max(deepest, level)
            pending.extend((child, level + 1) for child in node.children)
        return deepest

    def names(self, *kinds: str) -> list[str]:
        """Return names below this node narrowed to requested kinds."""
        wanted = kinds or None
        return [
            node.name
            for node in self.walk()
            if node.name and (wanted is None or node.kind in wanted)
        ]

    def of_kind(self, *kinds: str) -> list[SyntaxElement]:
        """Return every node below this one of a requested kind."""
        return [node for node in self.walk() if node.kind in kinds]

    def walk(self) -> Iterator[SyntaxElement]:
        """Yield this node and its descendants in source order."""
        pending: list[SyntaxElement] = [cast("SyntaxElement", self)]
        while pending:
            node = pending.pop()
            yield node
            pending.extend(reversed(node.children))
