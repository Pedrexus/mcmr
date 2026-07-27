from .bases import FrozenFlexModel


class GraphEdge(FrozenFlexModel):
    """Connect two stable graph node identifiers."""

    source: str
    target: str


class DirectedGraph(FrozenFlexModel):
    """Provide deterministic graph algorithms over a compact edge list."""

    edges: list[GraphEdge] = []

    def adjacency(self) -> dict[str, list[str]]:
        """Return what each node points at, in one pass over the edges.

        Reading the whole edge list once per node instead is quadratic, which nobody notices on a
        drawing of one neighborhood and which costs seconds on a monorepo whose module graph a
        repository-wide rule now walks in full.
        """
        found: dict[str, list[str]] = {
            endpoint: [] for edge in self.edges for endpoint in (edge.source, edge.target)
        }
        for edge in self.edges:
            found[edge.source].append(edge.target)
        return found

    def strongly_connected_components(self) -> list[list[str]]:
        """Return maximal mutually reachable node groups using Tarjan's algorithm.

        The depth-first walk carries its own stack rather than the interpreter's, because the
        deepest chain of imports in a large repository is bounded by nothing and a recursive walk
        would stop at whatever recursion limit the process happens to hold.
        """
        adjacency = self.adjacency()
        indices: dict[str, int] = {}
        lowlinks: dict[str, int] = {}
        path: list[str] = []
        active: set[str] = set()
        components: list[list[str]] = []
        for start in sorted(adjacency):
            if start in indices:
                continue
            pending: list[tuple[str, int]] = [(start, 0)]
            while pending:
                node, step = pending.pop()
                if step == 0:
                    indices[node] = lowlinks[node] = len(indices)
                    path.append(node)
                    active.add(node)
                descended = False
                for reached in range(step, len(adjacency[node])):
                    target = adjacency[node][reached]
                    if target not in indices:
                        pending += [(node, reached + 1), (target, 0)]
                        descended = True
                        break
                    if target in active:
                        lowlinks[node] = min(lowlinks[node], indices[target])
                if descended:
                    continue
                if lowlinks[node] == indices[node]:
                    components.append(self.settled(node, path, active))
                if pending:
                    holder = pending[-1][0]
                    lowlinks[holder] = min(lowlinks[holder], lowlinks[node])
        return components

    def settled(self, node: str, path: list[str], active: set[str]) -> list[str]:
        """Take the nodes above one root off the walk, which is the component it closed."""
        component: list[str] = []
        while True:
            member = path.pop()
            active.remove(member)
            component.append(member)
            if member == node:
                return component

    def cyclic_components(self) -> list[tuple[str, ...]]:
        """Return the components a path runs around, each with its members in name order.

        A group of two or more mutually reachable nodes is one, and so is a single node carrying
        an edge to itself, which Tarjan reports as a component of one exactly as it reports every
        node no cycle touches. The list is ordered so two runs over unchanged edges agree.
        """
        looping = {edge.source for edge in self.edges if edge.source == edge.target}
        return sorted(
            tuple(sorted(component))
            for component in self.strongly_connected_components()
            if len(component) > 1 or component[0] in looping
        )
