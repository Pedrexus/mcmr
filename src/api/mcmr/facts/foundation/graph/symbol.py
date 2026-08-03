from patos import FrozenModel

from .node import NodeRef


class SymbolRef(FrozenModel):
    """Address one resolved declaration together with every reference bound to it."""

    id: str
    name: str
    declaration: NodeRef
    references: list[NodeRef] = []
    are_references_complete: bool = False
