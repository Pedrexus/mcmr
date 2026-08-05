from patos import FrozenModel

from .edge import GraphEdge
from .traversal import Traversal


class DirectedGraph(FrozenModel):
    """Provide deterministic graph algorithms over a compact edge list."""

    edges: list[GraphEdge] = []

    def adjacency(self) -> dict[str, list[str]]:
        """Return what each node points at in one pass over the edges."""
        found: dict[str, list[str]] = {
            endpoint: [] for edge in self.edges for endpoint in (edge.source, edge.target)
        }
        for edge in self.edges:
            found[edge.source].append(edge.target)
        return found

    def strongly_connected_components(self) -> list[list[str]]:
        """Return maximal mutually reachable node groups using Tarjan's algorithm."""
        return Traversal(adjacency=self.adjacency()).components()
