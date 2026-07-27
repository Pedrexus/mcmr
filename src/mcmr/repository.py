from enum import StrEnum, auto
from typing import TYPE_CHECKING

from .bases import FrozenFlexModel
from .facts import ParameterKind, Visibility
from .protocol import KernelClient

if TYPE_CHECKING:
    from .protocol import KernelArgument


class Language(StrEnum):
    """Name the language that declared one symbol, since a monorepo names the same thing twice."""

    PYTHON = auto()
    RUST = auto()
    TYPESCRIPT = auto()
    C = auto()
    CPP = auto()
    CUDA = auto()

    @property
    def separator(self) -> str:
        """Return what this language writes between a holder and the name it holds."""
        return "." if self in {Language.PYTHON, Language.TYPESCRIPT} else "::"


class NodeKind(StrEnum):
    """Name what one node of the repository graph is, in the kernel's own vocabulary."""

    REPOSITORY = auto()
    DIRECTORY = auto()
    FILE = auto()
    MODULE = auto()
    CLASS = auto()
    FUNCTION = auto()
    METHOD = auto()
    PROPERTY = auto()
    ATTRIBUTE = auto()
    VARIABLE = auto()
    PARAMETER = auto()
    EXTERNAL_MODULE = "external-module"
    EXTERNAL_SYMBOL = "external-symbol"
    UNRESOLVED_SYMBOL = "unresolved-symbol"


class EdgeKind(StrEnum):
    """Name what one relationship between two graph nodes is."""

    CONTAIN = auto()
    DEFINE = auto()
    IMPORT = auto()
    CALL = auto()
    INSTANTIATE = auto()
    INHERIT = auto()
    TYPED = auto()
    ACCESS = auto()


class Resolution(StrEnum):
    """Say how completely one relationship was resolved."""

    EXACT = auto()
    EXTERNAL = auto()
    UNRESOLVED = auto()


class GraphNode(FrozenFlexModel):
    """Hold one node of the repository graph exactly as the kernel states it."""

    id: str
    kind: NodeKind
    qualname: str
    visibility: Visibility = Visibility.PUBLIC
    language: Language | None = None
    path: str | None = None
    is_package: bool = False
    line: int | None = None
    annotation: str | None = None
    return_annotation: str | None = None
    decorators: tuple[str, ...] = ()
    asynchronous: bool = False
    ordinal: int | None = None
    parameter_kind: ParameterKind | None = None
    has_default: bool = False
    is_abstract: bool = False

    @property
    def name(self) -> str:
        """Return the last segment of the qualified name, which is what a reader calls it.

        A node with no language is a place on disk rather than something a language declared, so
        what splits its name is the path separator.
        """
        separator = self.language.separator if self.language else "/"
        return self.qualname.rsplit(separator, 1)[-1]


class GraphRelation(FrozenFlexModel):
    """Hold one edge of the repository graph, beside the source site that stated it."""

    source: str
    target: str
    kind: EdgeKind
    path: str
    line: int
    resolution: Resolution


class RepositoryGraph(FrozenFlexModel):
    """Hold every node and every edge one kernel run found in a repository."""

    nodes: tuple[GraphNode, ...] = ()
    edges: tuple[GraphRelation, ...] = ()

    def index(self) -> dict[str, GraphNode]:
        """Return every node keyed by the stable identity its edges name it by."""
        return {node.id: node for node in self.nodes}

    def of_kind(self, kind: NodeKind) -> dict[str, GraphNode]:
        """Return the nodes of one kind, keyed by their stable identity."""
        return {node.id: node for node in self.nodes if node.kind is kind}


class GraphReader(KernelClient):
    """Ask the analysis kernel for the repository graph itself rather than for fact streams.

    The fact protocol answers with the families a rule reads, and a projection of the repository
    needs the graph behind them instead. The same request returns it when it asks, so this sends
    one request that names no family at all and validates the nodes and edges that come back.

    Every consumer that draws, ranks, or traverses the repository reads it through here. A second
    reader would mean a second copy of this wire vocabulary, and the two would drift the first time
    the kernel added a node kind.
    """

    def read(self) -> RepositoryGraph:
        """Run the kernel over the repository and return the graph it built."""
        request: dict[str, KernelArgument] = {"families": [], "graph": True}
        return RepositoryGraph.model_validate(self.ask(request).graph)
