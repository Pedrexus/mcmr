from patos import FrozenModel

from ....facts import ParameterKind, Visibility
from .kinds import EdgeKind, Language, NodeKind, Resolution


class _GraphRecords:
    """Own repository graph nodes, relations, and complete snapshots."""

    class NodeFields:
        """Group flat graph node fields by identity and declaration role."""

        class Identity(FrozenModel):
            """Retain stable identity, kind, visibility, language, and path."""

            id: str
            kind: NodeKind
            qualname: str
            visibility: Visibility = Visibility.PUBLIC
            language: Language | None = None
            path: str | None = None
            is_package: bool = False

        class Syntax(Identity):
            """Retain source annotations, decorators, order, and parameter kind."""

            line: int | None = None
            annotation: str | None = None
            return_annotation: str | None = None
            decorators: list[str] = []
            asynchronous: bool = False
            ordinal: int | None = None
            parameter_kind: ParameterKind | None = None

        class Role(Syntax):
            """Retain default, abstract contract, and enum declaration state."""

            has_default: bool = False
            is_abstract: bool = False
            is_enum: bool = False

    class Node(NodeFields.Role):
        """Hold one graph node exactly as the kernel states it."""

        @property
        def name(self) -> str:
            """Return the last segment of the qualified name."""
            separator = self.language.separator if self.language else "/"
            return self.qualname.rsplit(separator, 1)[-1]

    class Relation(FrozenModel):
        """Hold one graph edge beside the source site that stated it."""

        source: str
        target: str
        kind: EdgeKind
        path: str
        line: int
        resolution: Resolution

    class Graph(FrozenModel):
        """Hold every node and edge one kernel run found."""

        nodes: list[_GraphRecords.Node] = []
        edges: list[_GraphRecords.Relation] = []

        def index(self) -> dict[str, _GraphRecords.Node]:
            """Return every node keyed by stable identity."""
            return {node.id: node for node in self.nodes}

        def of_kind(self, kind: NodeKind) -> dict[str, _GraphRecords.Node]:
            """Return nodes of one kind keyed by stable identity."""
            return {node.id: node for node in self.nodes if node.kind is kind}


GraphNode = _GraphRecords.Node
GraphRelation = _GraphRecords.Relation
RepositoryGraph = _GraphRecords.Graph
