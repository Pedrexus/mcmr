import re
from abc import ABC, abstractmethod
from enum import StrEnum, auto
from typing import TYPE_CHECKING

from .bases import FrozenFlexModel
from .facts import Visibility
from .repository import EdgeKind, GraphNode, NodeKind, RepositoryGraph

if TYPE_CHECKING:
    from typing import ClassVar


class MemberKind(StrEnum):
    """Say which UML compartment one member of a class belongs in."""

    ATTRIBUTE = auto()
    METHOD = auto()


class RelationKind(StrEnum):
    """Say what one line drawn between two boxes means."""

    INHERIT = auto()
    IMPORT = auto()


class Member(FrozenFlexModel):
    """Name one member of a class, in the compartment and at the visibility it was declared."""

    name: str
    kind: MemberKind
    visibility: Visibility

    @property
    def marker(self) -> str:
        """Return the UML sigil for this visibility, which is what Pyreverse's four levels mean.

        Pyreverse sorts a name into public, protected, private, or special, and MCMR sorts it into
        four levels every language it reads can fill. A leading underscore is protected in both and
        a leading double underscore is private in both, so one internal or protected declaration
        takes the same `#` and everything left over reads as public.
        """
        match self.visibility:
            case Visibility.PUBLIC:
                return "+"
            case Visibility.PRIVATE:
                return "-"
            case _:
                return "#"

    def signature(self) -> str:
        """Return the member as UML writes it, which puts parentheses on a method."""
        return f"{self.name}()" if self.kind is MemberKind.METHOD else self.name


class DiagramNode(FrozenFlexModel):
    """One box of a diagram, keyed by the name the whole repository knows it by."""

    key: str
    label: str
    members: tuple[Member, ...] = ()


class DiagramEdge(FrozenFlexModel):
    """One line of a diagram, between the two boxes it names by their keys."""

    source: str
    target: str
    kind: RelationKind


class Diagram(FrozenFlexModel):
    """A whole diagram as a renderer needs it, with nothing left of the graph it came from.

    Everything here arrives sorted, so a renderer never decides an order of its own and two runs
    over unchanged source write the same bytes.
    """

    title: str
    nodes: tuple[DiagramNode, ...] = ()
    edges: tuple[DiagramEdge, ...] = ()


class DiagramKind(StrEnum):
    """Name one view of the repository graph."""

    CLASS = auto()
    PACKAGE = auto()


class DiagramBuilder(ABC):
    """Read one view of the repository graph out into a diagram.

    A further view arrives as a further subclass, which registers itself under the name the command
    line takes, so neither the graph reading nor any renderer changes to admit it.
    """

    kind: ClassVar[DiagramKind]
    builders: ClassVar[dict[DiagramKind, type[DiagramBuilder]]] = {}

    def __init_subclass__(cls) -> None:
        """Register one view under the kind it draws."""
        super().__init_subclass__()
        DiagramBuilder.builders[cls.kind] = cls

    @classmethod
    def of(cls, kind: DiagramKind) -> DiagramBuilder:
        """Return the builder that draws one kind of diagram."""
        return cls.builders[kind]()

    @abstractmethod
    def build(self, graph: RepositoryGraph) -> Diagram:
        """Return the diagram this view reads out of the graph."""


class ClassDiagram(DiagramBuilder):
    """Draw every class the repository declares, its own members, and what it inherits from.

    This is the diagram Pyreverse writes as `classes`, taken from the graph rather than from an
    inferring parser, and two differences are deliberate. Pyreverse infers the type of an attribute
    and prints it, while MCMR prints the names alone, because the graph records what the source
    states rather than what an inference engine concludes. Pyreverse also leaves an ancestor from
    outside the project out of the picture, and so does this, since a line to a base the repository
    does not hold would point at a box that is not drawn.
    """

    kind = DiagramKind.CLASS
    compartments: ClassVar[dict[NodeKind, MemberKind]] = {
        NodeKind.ATTRIBUTE: MemberKind.ATTRIBUTE,
        NodeKind.PROPERTY: MemberKind.ATTRIBUTE,
        NodeKind.METHOD: MemberKind.METHOD,
    }

    def build(self, graph: RepositoryGraph) -> Diagram:
        """Return one box per class, holding its members, joined by the inheritance it states."""
        classes = graph.of_kind(NodeKind.CLASS)
        held = self.members(graph, classes)
        inheritance = {
            DiagramEdge(
                source=classes[edge.source].qualname,
                target=classes[edge.target].qualname,
                kind=RelationKind.INHERIT,
            )
            for edge in graph.edges
            if edge.kind is EdgeKind.INHERIT and edge.source in classes and edge.target in classes
        }
        boxes = [
            DiagramNode(key=node.qualname, label=node.name, members=held[node.id])
            for node in sorted(classes.values(), key=lambda node: node.qualname)
        ]
        lines = sorted(inheritance, key=lambda edge: (edge.source, edge.target))
        return Diagram(title="classes", nodes=tuple(boxes), edges=tuple(lines))

    def members(
        self, graph: RepositoryGraph, classes: dict[str, GraphNode]
    ) -> dict[str, tuple[Member, ...]]:
        """Return what each class declares, with its attributes sorted ahead of its methods."""
        index = graph.index()
        held: dict[str, set[Member]] = {identity: set() for identity in classes}
        for edge in graph.edges:
            if edge.kind is not EdgeKind.DEFINE or edge.source not in held:
                continue
            declared = index[edge.target]
            if declared.kind in self.compartments:
                held[edge.source].add(
                    Member(
                        name=declared.name,
                        kind=self.compartments[declared.kind],
                        visibility=declared.visibility,
                    )
                )
        return {
            identity: tuple(
                sorted(members, key=lambda member: (member.kind is MemberKind.METHOD, member.name))
            )
            for identity, members in held.items()
        }


class PackageDiagram(DiagramBuilder):
    """Draw every module the repository holds and the imports that tie them to each other.

    This is the diagram Pyreverse writes as `packages`. Every import site between the same two
    modules aggregates into the one line that says the first depends on the second, so the diagram
    reports the dependency rather than how many times it was written. An import that leaves the
    repository has no box to point at and is left out, which is what Pyreverse does, and a module
    that names itself is dropped because that is not a dependency between two boxes.
    """

    kind = DiagramKind.PACKAGE

    def build(self, graph: RepositoryGraph) -> Diagram:
        """Return one box per module, joined by one line per pair of modules that import."""
        modules = graph.of_kind(NodeKind.MODULE)
        dependencies = {
            DiagramEdge(
                source=modules[edge.source].qualname,
                target=modules[edge.target].qualname,
                kind=RelationKind.IMPORT,
            )
            for edge in graph.edges
            if edge.kind is EdgeKind.IMPORT
            and edge.source in modules
            and edge.target in modules
            and edge.source != edge.target
        }
        boxes = [
            DiagramNode(key=node.qualname, label=node.qualname)
            for node in sorted(modules.values(), key=lambda node: node.qualname)
        ]
        lines = sorted(dependencies, key=lambda edge: (edge.source, edge.target))
        return Diagram(title="packages", nodes=tuple(boxes), edges=tuple(lines))


class DiagramFormat(StrEnum):
    """Name the notation one diagram is written in."""

    D2 = auto()
    MERMAID = auto()


class DiagramRenderer(ABC):
    """Write one diagram in a concrete notation.

    A renderer sees the diagram model and nothing else, so a further notation is a further subclass
    and touches neither the graph reading nor any view over it.
    """

    notation: ClassVar[DiagramFormat]
    renderers: ClassVar[dict[DiagramFormat, type[DiagramRenderer]]] = {}

    def __init_subclass__(cls) -> None:
        """Register one renderer under the notation it writes."""
        super().__init_subclass__()
        DiagramRenderer.renderers[cls.notation] = cls

    @classmethod
    def of(cls, notation: DiagramFormat) -> DiagramRenderer:
        """Return the renderer that writes one notation."""
        return cls.renderers[notation]()

    @abstractmethod
    def render(self, diagram: Diagram) -> str:
        """Return the whole diagram as the text of this notation."""


class D2Renderer(DiagramRenderer):
    """Write a diagram as D2, whose class shape takes the UML compartments as they are."""

    notation = DiagramFormat.D2
    arrows: ClassVar[dict[RelationKind, str]] = {
        RelationKind.INHERIT: "inherits",
        RelationKind.IMPORT: "imports",
    }

    def render(self, diagram: Diagram) -> str:
        """Return one class shape per box and one labeled connection per line."""
        shapes = [
            "\n".join(
                [
                    f'"{node.key}": {{',
                    f"  label: {node.label}",
                    "  shape: class",
                    *(f"  {self.row(member)}" for member in node.members),
                    "}",
                ]
            )
            for node in diagram.nodes
        ]
        connections = [
            f'"{edge.source}" -> "{edge.target}": {self.arrows[edge.kind]}'
            for edge in diagram.edges
        ]
        return "\n".join([f"# {diagram.title}", *shapes, *connections]) + "\n"

    def row(self, member: Member) -> str:
        """Return one member row, escaping the sigil D2 would otherwise read as a comment."""
        marker = "\\#" if member.marker == "#" else member.marker
        return f"{marker}{member.signature()}"


class MermaidRenderer(DiagramRenderer):
    """Write a diagram as a Mermaid class diagram, which is the notation Pyreverse calls `mmd`.

    Mermaid names a class with an identifier that holds no separator, so the qualified name becomes
    the label and a flattened form of it becomes the identity. Pyreverse instead shortens the name
    to its last segment, which quietly merges two classes of the same name in different modules.
    """

    notation = DiagramFormat.MERMAID
    arrows: ClassVar[dict[RelationKind, str]] = {
        RelationKind.INHERIT: "--|>",
        RelationKind.IMPORT: "-->",
    }

    def render(self, diagram: Diagram) -> str:
        """Return one class per box and one arrow per line, under a Mermaid title block."""
        classes = [
            "\n".join(
                [
                    f'  class {self.identifier(node.key)}["{node.label}"] {{',
                    *(f"    {self.row(member)}" for member in node.members),
                    "  }",
                ]
            )
            for node in diagram.nodes
        ]
        arrows = [
            f"  {self.identifier(edge.source)} {self.arrows[edge.kind]} "
            f"{self.identifier(edge.target)}"
            for edge in diagram.edges
        ]
        header = ["---", f"title: {diagram.title}", "---", "classDiagram"]
        return "\n".join([*header, *classes, *arrows]) + "\n"

    def identifier(self, key: str) -> str:
        """Return one qualified name as the plain identifier Mermaid accepts for a class."""
        return re.sub(r"[^0-9A-Za-z_]", "_", key)

    def row(self, member: Member) -> str:
        """Return one member row, escaping the underscore pairs Mermaid reads as emphasis."""
        return f"{member.marker}{member.signature().replace('__', r'\_\_')}"
