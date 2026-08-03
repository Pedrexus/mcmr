from typing import TYPE_CHECKING, ClassVar

from ....repository import EdgeKind, NodeKind
from ..kinds import DiagramKind, MemberKind
from ..models import DiagramNode, Member
from ..relations import RelationKind
from .base import DiagramBuilder

if TYPE_CHECKING:
    from collections.abc import Mapping

    from ....repository import GraphNode, RepositoryGraph


class ClassDiagram(DiagramBuilder):
    """Draw repository classes, their declared members, and inheritance."""

    kind = DiagramKind.CLASS
    title = "classes"
    node_kind = NodeKind.CLASS
    edge_kind = EdgeKind.INHERIT
    relation_kind = RelationKind.INHERIT
    compartments: ClassVar[dict[NodeKind, MemberKind]] = {
        NodeKind.ATTRIBUTE: MemberKind.ATTRIBUTE,
        NodeKind.PROPERTY: MemberKind.ATTRIBUTE,
        NodeKind.METHOD: MemberKind.METHOD,
    }

    def boxes(self, graph: RepositoryGraph, nodes: Mapping[str, GraphNode]) -> list[DiagramNode]:
        """Return class boxes with attributes before methods."""
        members = self.members(graph, nodes)
        return [
            DiagramNode(key=node.qualname, label=node.name, members=members[node.id])
            for node in sorted(nodes.values(), key=lambda item: item.qualname)
        ]

    def member(self, graph: RepositoryGraph, target: str) -> Member | None:
        """Return one drawable declared member when the graph target qualifies."""
        declared = graph.index()[target]
        return (
            Member(
                name=declared.name,
                kind=self.compartments[declared.kind],
                visibility=declared.visibility,
            )
            if declared.kind in self.compartments
            else None
        )

    def members(
        self, graph: RepositoryGraph, classes: Mapping[str, GraphNode]
    ) -> dict[str, list[Member]]:
        """Return the sorted members each class directly declares."""
        held: dict[str, set[Member]] = {identity: set() for identity in classes}
        for edge in graph.edges:
            if (
                edge.kind is EdgeKind.DEFINE
                and edge.source in held
                and (member := self.member(graph, edge.target))
            ):
                held[edge.source].add(member)
        return {
            identity: sorted(values, key=lambda item: (item.kind is MemberKind.METHOD, item.name))
            for identity, values in held.items()
        }
