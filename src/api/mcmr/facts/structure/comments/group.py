from typing import TYPE_CHECKING

from .groups import CommentGroupFields

if TYPE_CHECKING:
    from ...foundation import NodeRef


class CommentGroup(CommentGroupFields):
    """Retain measured sizes for one contiguous comment group."""

    parses_as_source: bool = False
    is_directive: bool = False
    node: NodeRef | None = None
