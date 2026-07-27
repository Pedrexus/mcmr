import heapq
from collections import deque
from enum import StrEnum, auto
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

from pydantic import NonNegativeInt, PositiveInt

from .bases import FrozenFlexModel
from .graph import DirectedGraph, GraphEdge
from .repository import EdgeKind, NodeKind, RepositoryGraph

if TYPE_CHECKING:
    from collections.abc import Sequence


class Dependency(FrozenFlexModel):
    """One module importing another, and where the repository states it."""

    importer: str
    imported: str
    path: str
    lines: tuple[NonNegativeInt, ...] = ()

    def location(self) -> str:
        """Name the file and the lines that state this import, for a report."""
        return f"{self.path}:{','.join(str(line) for line in self.lines)}"


class MatrixCell(FrozenFlexModel):
    """One filled entry of the matrix, where the row module imports the column module."""

    row: NonNegativeInt
    column: NonNegativeInt


class Cycle(FrozenFlexModel):
    """Modules that import each other, which no ordering can lay out as a layering."""

    members: tuple[str, ...]


class DesignStructureMatrix(FrozenFlexModel):
    """Every module on both axes, ordered so the layering of a repository is visible.

    A cell says the row module imports the column module. The ordering puts an importer
    ahead of what it imports, so a cell below the diagonal is a dependency pointing
    backwards, and only a cycle can produce one. Those are the entries a reader is looking
    for, so `back_edges` names them beside the file and line that state them rather than
    leaving them to be spotted in the grid.
    """

    ordering: tuple[str, ...] = ()
    cells: tuple[MatrixCell, ...] = ()
    cycles: tuple[Cycle, ...] = ()
    back_edges: tuple[Dependency, ...] = ()


class ReachedModule(FrozenFlexModel):
    """One module that reaches a change, and how many imports away from it that module sits."""

    module: str
    path: str
    distance: NonNegativeInt


class ImpactSet(FrozenFlexModel):
    """What a change to one set of files could break.

    `reached` holds every module with an import path to a changed one, nearest first, which
    is the answer to what this edit could break. A path the graph does not name is reported
    as unresolved rather than dropped, since a file outside the graph would otherwise read
    as a change nothing depends on.
    """

    changed: tuple[str, ...] = ()
    unresolved: tuple[str, ...] = ()
    reached: tuple[ReachedModule, ...] = ()


class ModuleGraph(FrozenFlexModel):
    """The import projection of the repository graph, over the modules a repository owns.

    Both views below project the graph the kernel already builds rather than analyzing the
    source a second time, which is why they belong beside it. A module is a row of the matrix
    and a step of the impact walk, and an import between two of them is the only relationship
    either one reads.
    """

    root: Path
    paths: dict[str, str] = {}
    dependencies: tuple[Dependency, ...] = ()

    @classmethod
    def of(cls, repository: RepositoryGraph, root: Path) -> ModuleGraph:
        """Keep the module nodes of a repository graph and the imports that relate them.

        Every other node kind and every other edge kind is dropped, since a design structure
        matrix and a blast radius are both statements about modules importing each other. An
        import of a package the repository does not own goes with them, because a row nobody
        can edit is not a row worth reading. Two source sites stating the same import become
        one dependency carrying both lines, since the matrix holds one cell for the pair.
        """
        modules = repository.of_kind(NodeKind.MODULE)
        paths = {node.qualname: node.path or "" for node in modules.values()}
        sites: dict[tuple[str, str], set[int]] = {}
        for edge in repository.edges:
            if edge.kind is EdgeKind.IMPORT and edge.source in modules and edge.target in modules:
                pair = (modules[edge.source].qualname, modules[edge.target].qualname)
                sites.setdefault(pair, set()).add(edge.line)
        return cls(
            root=root,
            paths=paths,
            dependencies=tuple(
                Dependency(
                    importer=importer,
                    imported=imported,
                    path=paths[importer],
                    lines=tuple(sorted(lines)),
                )
                for (importer, imported), lines in sorted(sites.items())
            ),
        )

    def matrix(self) -> DesignStructureMatrix:
        """Lay every module on both axes in the ordering that makes the layering visible.

        The modules that import each other are grouped first, since a cycle is the one thing
        an ordering cannot lay out, and the groups are then ordered so every importer comes
        ahead of what it imports. A dependency that still points backwards from there runs
        inside a cycle, and the matrix names it.
        """
        clusters = self.layered(self.clusters())
        ordering = [module for cluster in clusters for module in cluster]
        position = {module: index for index, module in enumerate(ordering)}
        return DesignStructureMatrix(
            ordering=tuple(ordering),
            cells=tuple(
                MatrixCell(row=row, column=column)
                for row, column in sorted(
                    (position[edge.importer], position[edge.imported])
                    for edge in self.dependencies
                )
            ),
            cycles=tuple(Cycle(members=cluster) for cluster in clusters if len(cluster) > 1),
            back_edges=tuple(
                edge
                for edge in self.dependencies
                if position[edge.importer] > position[edge.imported]
            ),
        )

    def impact(self, changed: Sequence[Path]) -> ImpactSet:
        """Walk up the imports from every changed file and report what reaches it.

        The walk runs one breadth-first pass over the reversed import edges from all the
        changed modules at once, so a module is reported once at the fewest imports that
        reach any of the changes. Only a changed module sits at no distance at all, which is
        what keeps a change out of its own blast radius.
        """
        owners = {(self.root / path).resolve(): module for module, path in self.paths.items()}
        named = {path: owners.get(path.resolve()) for path in changed}
        origins = sorted({module for module in named.values() if module is not None})
        importers = self.importers()
        distance = dict.fromkeys(origins, 0)
        pending = deque(origins)
        while pending:
            module = pending.popleft()
            for importer in importers.get(module, ()):
                if importer not in distance:
                    distance[importer] = distance[module] + 1
                    pending.append(importer)
        return ImpactSet(
            changed=tuple(origins),
            unresolved=tuple(
                sorted(str(path) for path, module in named.items() if module is None)
            ),
            reached=tuple(
                ReachedModule(module=module, path=self.paths[module], distance=hops)
                for module, hops in sorted(
                    distance.items(), key=lambda found: (found[1], found[0])
                )
                if hops
            ),
        )

    def clusters(self) -> list[tuple[str, ...]]:
        """Group the modules that import each other, leaving every other module on its own.

        A cycle occupies one position of the matrix with its members alphabetical inside it,
        which is the stable ordering to give a group whose members no dependency separates.
        """
        connected = DirectedGraph(
            edges=[
                GraphEdge(source=edge.importer, target=edge.imported) for edge in self.dependencies
            ]
        ).strongly_connected_components()
        grouped = {module for component in connected for module in component}
        return sorted(
            [tuple(sorted(component)) for component in connected]
            + [(module,) for module in self.paths if module not in grouped]
        )

    def layered(self, clusters: list[tuple[str, ...]]) -> list[tuple[str, ...]]:
        """Order the clusters so every importer comes ahead of what it imports.

        Kahn's algorithm over the clusters, always taking the alphabetically first cluster
        whose importers are all placed already, so the result is a topological ordering
        wherever the graph admits one and is identical on every run over unchanged source.
        """
        holder = {module: cluster for cluster in clusters for module in cluster}
        crossing = {
            (holder[edge.importer], holder[edge.imported])
            for edge in self.dependencies
            if holder[edge.importer] != holder[edge.imported]
        }
        waiting = dict.fromkeys(clusters, 0)
        following: dict[tuple[str, ...], list[tuple[str, ...]]] = {
            cluster: [] for cluster in clusters
        }
        for importer, imported in sorted(crossing):
            following[importer].append(imported)
            waiting[imported] += 1
        ready = [cluster for cluster in clusters if not waiting[cluster]]
        heapq.heapify(ready)
        ordered: list[tuple[str, ...]] = []
        while ready:
            cluster = heapq.heappop(ready)
            ordered.append(cluster)
            for follower in following[cluster]:
                waiting[follower] -= 1
                if not waiting[follower]:
                    heapq.heappush(ready, follower)
        return ordered

    def importers(self) -> dict[str, list[str]]:
        """Return, for every module, the modules that import it, in a stable order."""
        found: dict[str, list[str]] = {}
        for edge in self.dependencies:
            found.setdefault(edge.imported, []).append(edge.importer)
        return {module: sorted(names) for module, names in found.items()}


class Rendering[Projection](Protocol):
    """Turn one projection into the text a reader or another tool consumes.

    Rendering is separate from the traversal on purpose, so a new view of either projection
    is a new class here and never a change to how the graph is walked.
    """

    def render(self, projection: Projection) -> str:
        """Return the whole projection as text."""
        ...


class JsonRendering(FrozenFlexModel):
    """Render any projection as the JSON a tool reads, in the field order its model states."""

    def render(self, projection: FrozenFlexModel) -> str:
        """Return the projection as indented JSON."""
        return projection.model_dump_json(indent=2)


class MatrixText(FrozenFlexModel):
    """Render the matrix as a grid a terminal holds, with the back edges named beneath it.

    The grid carries index numbers rather than names so it stays narrow, and the legend above
    it says which module each index is. A repository with more modules than the limit gets
    the first ones in the ordering, which are the ones nothing else depends on.
    """

    limit: PositiveInt = 32

    def render(self, projection: DesignStructureMatrix) -> str:
        """Draw the legend, the grid, the cycles, and the dependencies pointing backwards."""
        shown = projection.ordering[: self.limit]
        filled = {(cell.row, cell.column) for cell in projection.cells}
        width = len(str(len(shown)))
        step = width + 1
        lines = [
            f"Design structure matrix over {len(projection.ordering)} modules "
            f"and {len(projection.cells)} dependencies",
            "",
            *(f"{index + 1:>{width}} {module}" for index, module in enumerate(shown)),
            "",
            " " * width + "".join(f"{index + 1:>{step}}" for index in range(len(shown))),
        ]
        lines += [
            f"{row + 1:>{width}}"
            + "".join(f"{self.glyph(row, column, filled):>{step}}" for column in range(len(shown)))
            for row in range(len(shown))
        ]
        lines += self.section("Cycles", [" ".join(cycle.members) for cycle in projection.cycles])
        lines += self.section(
            "Back edges",
            [
                f"{edge.importer} imports {edge.imported} at {edge.location()}"
                for edge in projection.back_edges
            ],
        )
        omitted = len(projection.ordering) - len(shown)
        if omitted:
            lines += ["", f"{omitted} more modules follow these in the ordering"]
        return "\n".join(lines)

    def glyph(self, row: int, column: int, filled: set[tuple[int, int]]) -> str:
        """Say what one entry of the grid holds, marking a backwards dependency apart."""
        if row == column:
            return "\\"
        if (row, column) not in filled:
            return "."
        return "<" if row > column else "X"

    def section(self, title: str, entries: list[str]) -> list[str]:
        """Return one titled block beneath the grid, bounded by the same limit.

        A block with nothing in it still states its count, since finding no cycle and no
        backwards dependency is the news a reader of a matrix came for.
        """
        shown = entries[: self.limit]
        omitted = len(entries) - len(shown)
        return [
            "",
            f"{title} ({len(entries)})",
            *(f"  {entry}" for entry in shown),
            *([f"  and {omitted} more"] if omitted else []),
        ]


class ImpactText(FrozenFlexModel):
    """Render the impact set as the modules a change could break, nearest first."""

    def render(self, projection: ImpactSet) -> str:
        """State what changed, what no module owns, and what reaches the change."""
        width = max((len(item.module) for item in projection.reached), default=0)
        return "\n".join(
            [
                f"{len(projection.changed)} changed, {len(projection.reached)} modules "
                f"reach them through imports",
                "",
                *(f"  changed {module}" for module in projection.changed),
                *(f"  unresolved {path}" for path in projection.unresolved),
                "",
                "hops  module",
                *(
                    f"{item.distance:>4}  {item.module.ljust(width)}  {item.path}"
                    for item in projection.reached
                ),
            ]
        )


class ProjectionFormat(StrEnum):
    """Say whether a projection is rendered for a person reading it or for another tool.

    The format picks the rendering rather than the command doing it, so a third format is a
    member here beside a class of its own and reaches both projections at once.
    """

    TEXT = auto()
    JSON = auto()

    def matrix(self, limit: int) -> Rendering[DesignStructureMatrix]:
        """Return the rendering a design structure matrix takes in this format."""
        return MatrixText(limit=limit) if self is ProjectionFormat.TEXT else JsonRendering()

    def impact(self) -> Rendering[ImpactSet]:
        """Return the rendering an impact set takes in this format."""
        return ImpactText() if self is ProjectionFormat.TEXT else JsonRendering()
