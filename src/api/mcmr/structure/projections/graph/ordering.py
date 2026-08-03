import heapq
from typing import TYPE_CHECKING

from patos import FrozenModel

from ....repository import DirectedGraph, GraphEdge
from ..contracts import Dependency

if TYPE_CHECKING:
    from collections.abc import Collection, Mapping, MutableSequence, Sequence


class ModuleOrdering(FrozenModel):
    """Order modules topologically while retaining strongly connected groups."""

    paths: dict[str, str]
    dependencies: list[Dependency]

    @staticmethod
    def schedule(
        crossings: Collection[tuple[int, int]], count: int
    ) -> tuple[list[int], list[list[int]]]:
        """Return incoming counts and outgoing group edges for Kahn ordering."""
        waiting = [0 for _ in range(count)]
        following: list[list[int]] = [[] for _ in range(count)]
        for importer, imported in sorted(crossings):
            following[importer].append(imported)
            waiting[imported] += 1
        return waiting, following

    def clusters(self) -> list[list[str]]:
        """Return strongly connected modules and standalone modules as stable groups."""
        connected = DirectedGraph(
            edges=[
                GraphEdge(source=edge.importer, target=edge.imported) for edge in self.dependencies
            ]
        ).strongly_connected_components()
        grouped = {module for component in connected for module in component}
        singles = [[module] for module in self.paths if module not in grouped]
        return sorted([sorted(component) for component in connected] + singles)

    def crossings(self, holder: Mapping[str, int]) -> set[tuple[int, int]]:
        """Return dependency edges that cross between connected groups."""
        return {
            (holder[edge.importer], holder[edge.imported])
            for edge in self.dependencies
            if holder[edge.importer] != holder[edge.imported]
        }

    def drain(
        self,
        *,
        clusters: Sequence[Sequence[str]],
        following: Sequence[Sequence[int]],
        ready: list[int],
        waiting: MutableSequence[int],
    ) -> list[list[str]]:
        """Drain ready groups in stable order while releasing their dependencies."""
        ordered: list[list[str]] = []
        while ready:
            cluster_index = heapq.heappop(ready)
            ordered.append(list(clusters[cluster_index]))
            for follower in following[cluster_index]:
                waiting[follower] -= 1
                if not waiting[follower]:
                    heapq.heappush(ready, follower)
        return ordered

    def layered(self, clusters: Sequence[Sequence[str]]) -> list[list[str]]:
        """Apply stable Kahn ordering to strongly connected groups."""
        holder = {
            module: cluster_index
            for cluster_index, cluster in enumerate(clusters)
            for module in cluster
        }
        waiting, following = self.schedule(self.crossings(holder), len(clusters))
        ready = [index for index, count in enumerate(waiting) if not count]
        heapq.heapify(ready)
        return self.drain(
            clusters=clusters,
            following=following,
            ready=ready,
            waiting=waiting,
        )

    def ordered(self) -> list[list[str]]:
        """Return every connected group in stable dependency order."""
        return self.layered(self.clusters())
