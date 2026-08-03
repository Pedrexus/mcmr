from patos import FrozenModel

from ..relations import RelationKind


class DiagramEdge(FrozenModel):
    """Hold one typed line between two diagram boxes."""

    source: str
    target: str
    kind: RelationKind
