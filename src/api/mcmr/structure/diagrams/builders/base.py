from typing import TYPE_CHECKING, ClassVar

from patos import Registry

from ..models import Diagram, DiagramEdge, DiagramNode

if TYPE_CHECKING:
    from collections.abc import Mapping

    from ....repository import EdgeKind, GraphNode, NodeKind, RepositoryGraph
    from ..kinds import DiagramKind
    from ..relations import RelationKind


class DiagramBuilder(Registry):
    """Build one registered view from the language-neutral repository graph."""

    kind: ClassVar[DiagramKind]
    title: ClassVar[str]
    node_kind: ClassVar[NodeKind]
    edge_kind: ClassVar[EdgeKind]
    relation_kind: ClassVar[RelationKind]
    qualified_labels: ClassVar[bool] = False
    exclude_self: ClassVar[bool] = False

    @classmethod
    def of(cls, kind: DiagramKind) -> DiagramBuilder:
        """Return the builder registered for one diagram kind."""
        return cls.find(kind, attr="kind")()

    def boxes(self, graph: RepositoryGraph, nodes: Mapping[str, GraphNode]) -> list[DiagramNode]:
        """Return the sorted boxes for this view."""
        return [
            DiagramNode(
                key=node.qualname,
                label=node.qualname if self.qualified_labels else node.name,
            )
            for node in sorted(nodes.values(), key=lambda item: item.qualname)
        ]

    def build(self, graph: RepositoryGraph) -> Diagram:
        """Return this view of one repository graph."""
        nodes = graph.of_kind(self.node_kind)
        return Diagram(
            title=self.title,
            nodes=self.boxes(graph, nodes),
            edges=self.lines(graph, nodes),
        )

    def lines(self, graph: RepositoryGraph, nodes: Mapping[str, GraphNode]) -> list[DiagramEdge]:
        """Return the sorted internal relations this view draws."""
        edges = {
            DiagramEdge(
                source=nodes[edge.source].qualname,
                target=nodes[edge.target].qualname,
                kind=self.relation_kind,
            )
            for edge in graph.edges
            if edge.kind is self.edge_kind
            and edge.source in nodes
            and edge.target in nodes
            and (not self.exclude_self or edge.source != edge.target)
        }
        return sorted(edges, key=lambda edge: (edge.source, edge.target))
