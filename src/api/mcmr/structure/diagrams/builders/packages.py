from ....repository import EdgeKind, NodeKind
from ..kinds import DiagramKind
from ..relations import RelationKind
from .base import DiagramBuilder


class PackageDiagram(DiagramBuilder):
    """Draw repository modules and the imports between them."""

    kind = DiagramKind.PACKAGE
    title = "packages"
    node_kind = NodeKind.MODULE
    edge_kind = EdgeKind.IMPORT
    relation_kind = RelationKind.IMPORT
    qualified_labels = True
    exclude_self = True
