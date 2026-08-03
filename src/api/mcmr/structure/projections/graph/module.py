from pathlib import Path
from typing import TYPE_CHECKING

from patos import FrozenModel

from ....repository import EdgeKind, NodeKind
from ..contracts import Cycle, Dependency
from ..matrices import DesignStructureMatrix, MatrixCell
from .impact import ImpactTraversal
from .ordering import ModuleOrdering

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from ....repository import GraphNode, RepositoryGraph
    from ..impacts import ImpactSet


class ModuleGraph(FrozenModel):
    """Hold the editable module and import projection of a repository graph."""

    root: Path
    paths: dict[str, str] = {}
    dependencies: list[Dependency] = []

    @classmethod
    def dependency_records(
        cls,
        repository: RepositoryGraph,
        *,
        modules: Mapping[str, GraphNode],
        paths: Mapping[str, str],
    ) -> list[Dependency]:
        """Aggregate import sites into one dependency per module pair."""
        sites: dict[tuple[str, str], set[int]] = {}
        for edge in repository.edges:
            if edge.kind is EdgeKind.IMPORT and edge.source in modules and edge.target in modules:
                pair = (modules[edge.source].qualname, modules[edge.target].qualname)
                sites.setdefault(pair, set()).add(edge.line)
        return [
            Dependency(importer=source, imported=target, path=paths[source], lines=sorted(lines))
            for (source, target), lines in sorted(sites.items())
        ]

    @classmethod
    def of(cls, repository: RepositoryGraph, root: Path) -> ModuleGraph:
        """Project repository modules and their internal imports into one graph."""
        modules = repository.of_kind(NodeKind.MODULE)
        paths = {node.qualname: node.path or "" for node in modules.values()}
        return cls(
            root=root,
            paths=paths,
            dependencies=cls.dependency_records(repository, modules=modules, paths=paths),
        )

    def back_edges(self, position: Mapping[str, int]) -> list[Dependency]:
        """Return dependencies that still point backwards after ordering."""
        return [
            edge for edge in self.dependencies if position[edge.importer] > position[edge.imported]
        ]

    def cells(self, position: Mapping[str, int]) -> list[MatrixCell]:
        """Return sorted matrix cells for every dependency."""
        pairs = sorted(
            (position[edge.importer], position[edge.imported]) for edge in self.dependencies
        )
        return [MatrixCell(row=row, column=column) for row, column in pairs]

    def impact(self, changed: Sequence[Path]) -> ImpactSet:
        """Walk reversed imports from every changed path."""
        traversal = ImpactTraversal(
            root=self.root, paths=self.paths, dependencies=self.dependencies
        )
        return traversal.walk(changed)

    def importers(self) -> dict[str, list[str]]:
        """Return the sorted modules that import each module."""
        traversal = ImpactTraversal(
            root=self.root, paths=self.paths, dependencies=self.dependencies
        )
        return traversal.importers()

    def matrix(self) -> DesignStructureMatrix:
        """Lay every module on both axes so its dependency layering is visible."""
        clusters = ModuleOrdering(paths=self.paths, dependencies=self.dependencies).ordered()
        ordering = [module for cluster in clusters for module in cluster]
        position = {module: index for index, module in enumerate(ordering)}
        return DesignStructureMatrix(
            ordering=ordering,
            cells=self.cells(position),
            cycles=[Cycle(members=cluster) for cluster in clusters if len(cluster) > 1],
            back_edges=self.back_edges(position),
        )
