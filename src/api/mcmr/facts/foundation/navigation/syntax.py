from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from ..span import SourceSpan


class SyntaxElement(Protocol):
    """Expose only the syntax navigation every rule needs from a node representation."""

    @property
    def children(self) -> Sequence[SyntaxElement]: ...

    @property
    def depth(self) -> int: ...

    @property
    def kind(self) -> str: ...

    @property
    def name(self) -> str: ...

    @property
    def span(self) -> SourceSpan | None: ...

    @property
    def text(self) -> str: ...

    def names(self, *kinds: str) -> list[str]: ...

    def of_kind(self, *kinds: str) -> Sequence[SyntaxElement]: ...

    def walk(self) -> Iterator[SyntaxElement]: ...
