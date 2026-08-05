from patos import FrozenModel


class GraphEdge(FrozenModel):
    """Connect two stable graph node identifiers."""

    source: str
    target: str
