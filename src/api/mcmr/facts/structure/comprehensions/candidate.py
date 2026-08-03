from typing import TYPE_CHECKING

from .groups import SetLoopFields

if TYPE_CHECKING:
    from ...foundation import NodeRef


class SetLoopCandidate(SetLoopFields):
    """Retain one set initialization and a convertible following loop."""

    loop: NodeRef | None = None
    element: NodeRef | None = None
    target: NodeRef | None = None
    iterable: NodeRef | None = None
    conditions: list[NodeRef] = []
