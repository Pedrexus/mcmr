from typing import Literal

from patos import FrozenModel

from .....facts import NodeRef, SourceSpan, SymbolRef
from ..imports import ImportRequest, Placement


class _RewriteTypes:
    """Own the closed source rewrite vocabulary used by one fix plan."""

    class Remove(FrozenModel):
        """Delete one node and the trivia that only exists to hold it."""

        kind: Literal["remove"] = "remove"
        target: NodeRef

        @property
        def spans(self) -> list[SourceSpan]:
            """Return the removed node span."""
            return [self.target.span]

    class RemoveDirectory(FrozenModel):
        """Remove one repository directory only while it remains empty."""

        kind: Literal["remove-directory"] = "remove-directory"
        target: SourceSpan

        @property
        def spans(self) -> list[SourceSpan]:
            """Return the removed directory path as retained evidence."""
            return [self.target]

    class Replace(FrozenModel):
        """Replace one node with validated source."""

        kind: Literal["replace"] = "replace"
        target: NodeRef
        source: str
        imports: list[ImportRequest] = []

        @property
        def spans(self) -> list[SourceSpan]:
            """Return the replaced node span."""
            return [self.target.span]

    class Unwrap(FrozenModel):
        """Replace one node with a descendant it already contains."""

        kind: Literal["unwrap"] = "unwrap"
        target: NodeRef
        keep: NodeRef

        @property
        def spans(self) -> list[SourceSpan]:
            """Return the unwrapped node span."""
            return [self.target.span]

    class Inline(FrozenModel):
        """Replace references with a declaration body, then remove the declaration."""

        kind: Literal["inline"] = "inline"
        declaration: NodeRef
        body: NodeRef
        references: list[NodeRef]

        @property
        def spans(self) -> list[SourceSpan]:
            """Return the declaration span and every edited reference span."""
            return [self.declaration.span, *(reference.span for reference in self.references)]

    class Move(FrozenModel):
        """Relocate one existing node beside an anchor."""

        kind: Literal["move"] = "move"
        target: NodeRef
        anchor: NodeRef
        placement: Placement
        prefix: str = ""
        imports: list[ImportRequest] = []

        @property
        def spans(self) -> list[SourceSpan]:
            """Return the moved node span and destination anchor span."""
            return [self.target.span, self.anchor.span]

    class Rename(FrozenModel):
        """Rename one resolved symbol and every bound reference."""

        kind: Literal["rename"] = "rename"
        symbol: SymbolRef
        name: str

        @property
        def spans(self) -> list[SourceSpan]:
            """Return the declaration span and every reference span."""
            return [
                self.symbol.declaration.span,
                *(reference.span for reference in self.symbol.references),
            ]


Inline = _RewriteTypes.Inline
Move = _RewriteTypes.Move
Remove = _RewriteTypes.Remove
RemoveDirectory = _RewriteTypes.RemoveDirectory
Rename = _RewriteTypes.Rename
Replace = _RewriteTypes.Replace
Unwrap = _RewriteTypes.Unwrap
