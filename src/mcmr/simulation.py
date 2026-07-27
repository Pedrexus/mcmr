from collections import deque
from enum import StrEnum, auto
from typing import TYPE_CHECKING

from pydantic import NonNegativeInt

from .bases import FrozenFlexModel
from .projections import Cycle, Dependency, JsonRendering, ModuleGraph, Rendering
from .runs import section

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence


class ProposedImport(FrozenFlexModel):
    """One import a caller is asking about, before the graph has said whether it knows it."""

    importer: str
    imported: str

    @classmethod
    def parse(cls, specification: str) -> ProposedImport:
        """Read one `importer:imported` pair, since a module name never holds a colon."""
        parts = specification.split(":")
        if len(parts) != 2 or not all(parts):
            raise ValueError(f"an import reads as `importer:imported`, not {specification!r}")
        return cls(importer=parts[0], imported=parts[1])

    def arrow(self) -> str:
        """Return this import the way a reader reads it."""
        return f"{self.importer} imports {self.imported}"


class AppliedChange(FrozenFlexModel):
    """What the question amounted to once the graph resolved every name in it.

    Nothing is dropped silently. A name the repository does not own, an import that was already
    there or already absent, and an import stated as both an addition and a removal are all echoed
    back, because a report that quietly discarded them would answer a question nobody asked.
    """

    added: tuple[ProposedImport, ...] = ()
    removed: tuple[ProposedImport, ...] = ()
    unchanged: tuple[ProposedImport, ...] = ()
    cancelled: tuple[ProposedImport, ...] = ()
    unknown: tuple[str, ...] = ()


class Simulation(FrozenFlexModel):
    """What a repository would look like with these imports, without a file being touched.

    Only the structural answer is here. MCMR judges facts extracted from source, and a hypothetical
    import has no source behind it, so this states what the import graph would become and stops
    short of a verdict the rules were never run to reach.
    """

    applied: AppliedChange
    cycles_formed: tuple[Cycle, ...] = ()
    cycles_broken: tuple[Cycle, ...] = ()
    back_edges_formed: tuple[Dependency, ...] = ()
    back_edges_cleared: tuple[Dependency, ...] = ()
    propagation_before: float = 0.0
    propagation_after: float = 0.0


class ImportProposal(FrozenFlexModel):
    """Ask what the import graph would become if these imports existed, and answer without editing.

    This is a question about structure rather than about history, which is why it reads the same
    projection the design structure matrix and the blast radius already read. Applying the change
    to a copy of that projection is the whole mechanism, so the answer stays exactly as trustworthy
    as the graph the kernel built and never needs a second traversal of its own.
    """

    graph: ModuleGraph
    added: tuple[ProposedImport, ...] = ()
    removed: tuple[ProposedImport, ...] = ()

    def run(self) -> Simulation:
        """Apply what the graph can apply and report what the repository would become."""
        applied = self.resolve()
        hypothetical = self.hypothetical(applied)
        before, after = self.graph.matrix(), hypothetical.matrix()
        known = {frozenset(cycle.members) for cycle in before.cycles}
        proposed = {frozenset(cycle.members) for cycle in after.cycles}
        return Simulation(
            applied=applied,
            cycles_formed=tuple(
                cycle for cycle in after.cycles if frozenset(cycle.members) not in known
            ),
            cycles_broken=tuple(
                cycle for cycle in before.cycles if frozenset(cycle.members) not in proposed
            ),
            back_edges_formed=arriving(after.back_edges, before.back_edges),
            back_edges_cleared=arriving(before.back_edges, after.back_edges),
            propagation_before=propagation(self.graph),
            propagation_after=propagation(hypothetical),
        )

    def resolve(self) -> AppliedChange:
        """Sort every proposed import into one the graph can apply, cannot name, or already holds.

        An import stated as both an addition and a removal cancels, because applying both would
        leave the graph exactly as it was and reporting both would claim two changes that never
        happened.
        """
        named = set(self.graph.paths)
        present = {(item.importer, item.imported) for item in self.graph.dependencies}
        adding = pairs(self.added, named)
        removing = pairs(self.removed, named)
        return AppliedChange(
            added=proposals(sorted(adding - removing - present)),
            removed=proposals(sorted((removing - adding) & present)),
            unchanged=proposals(
                sorted(((adding - removing) & present) | ((removing - adding) - present))
            ),
            cancelled=proposals(sorted(adding & removing)),
            unknown=tuple(
                sorted(
                    {
                        name
                        for item in (*self.added, *self.removed)
                        for name in (item.importer, item.imported)
                        if name not in named
                    }
                )
            ),
        )

    def hypothetical(self, applied: AppliedChange) -> ModuleGraph:
        """Return the same projection with these imports present and those imports gone."""
        dropped = {(item.importer, item.imported) for item in applied.removed}
        kept = [
            item
            for item in self.graph.dependencies
            if (item.importer, item.imported) not in dropped
        ]
        invented = [
            Dependency(
                importer=item.importer,
                imported=item.imported,
                path=self.graph.paths[item.importer],
            )
            for item in applied.added
        ]
        ordered = sorted(kept + invented, key=lambda item: (item.importer, item.imported))
        return ModuleGraph(
            root=self.graph.root, paths=self.graph.paths, dependencies=tuple(ordered)
        )


class SimulationFormat(StrEnum):
    """Say whether a simulation is rendered for a person reading it or for another tool."""

    TEXT = auto()
    JSON = auto()

    def simulation(self, limit: int) -> Rendering[Simulation]:
        """Return the rendering a simulation takes in this format."""
        return SimulationText(limit=limit) if self is SimulationFormat.TEXT else JsonRendering()


class SimulationText(FrozenFlexModel):
    """Render a simulation as what the proposed imports would do to the shape of a repository."""

    limit: NonNegativeInt = 10

    def render(self, projection: Simulation) -> str:
        """State what was applied, then what it would form, break, and cost."""
        applied = projection.applied
        moved = projection.propagation_after - projection.propagation_before
        lines = [
            f"{len(applied.added)} imports added and {len(applied.removed)} removed, "
            f"in the graph alone, with no file touched",
            "",
            f"propagation cost {projection.propagation_before:.4f} becomes "
            f"{projection.propagation_after:.4f} ({moved:+.4f})",
        ]
        lines += section("Added", (item.arrow() for item in applied.added), self.limit)
        lines += section("Removed", (item.arrow() for item in applied.removed), self.limit)
        lines += section(
            "Already as asked", (item.arrow() for item in applied.unchanged), self.limit
        )
        lines += section(
            "Stated both ways", (item.arrow() for item in applied.cancelled), self.limit
        )
        lines += section("Unknown modules", applied.unknown, self.limit)
        lines += section(
            "Cycles formed",
            (" ".join(cycle.members) for cycle in projection.cycles_formed),
            self.limit,
        )
        lines += section(
            "Cycles broken",
            (" ".join(cycle.members) for cycle in projection.cycles_broken),
            self.limit,
        )
        lines += section(
            "Back edges formed",
            (f"{item.importer} imports {item.imported}" for item in projection.back_edges_formed),
            self.limit,
        )
        lines += section(
            "Back edges cleared",
            (f"{item.importer} imports {item.imported}" for item in projection.back_edges_cleared),
            self.limit,
        )
        return "\n".join(lines)


def pairs(items: Sequence[ProposedImport], named: set[str]) -> set[tuple[str, str]]:
    """Return the proposed imports whose two ends are both modules this repository owns."""
    return {
        (item.importer, item.imported)
        for item in items
        if item.importer in named and item.imported in named
    }


def proposals(named: Iterable[tuple[str, str]]) -> tuple[ProposedImport, ...]:
    """Return one proposed import per named pair, in the order they arrive."""
    return tuple(
        ProposedImport(importer=importer, imported=imported) for importer, imported in named
    )


def arriving(
    subject: Sequence[Dependency], against: Sequence[Dependency]
) -> tuple[Dependency, ...]:
    """Return the dependencies one side holds and the other does not, by the pair they name."""
    held = {(item.importer, item.imported) for item in against}
    return tuple(item for item in subject if (item.importer, item.imported) not in held)


def propagation(graph: ModuleGraph) -> float:
    """Return the share of a repository one edit reaches on average.

    This is MacCormack's propagation cost, the sum over every module of how many modules reach it
    through imports counting itself, divided by the square of the module count. It is the number
    that says whether a proposed import left the repository more entangled than it found it, and it
    is the same figure Archy reports for the same graph.
    """
    importers = graph.importers()
    modules = sorted(graph.paths)
    if not modules:
        return 0.0
    total = 0
    for module in modules:
        reached = {module}
        pending = deque([module])
        while pending:
            for above in importers.get(pending.popleft(), ()):
                if above not in reached:
                    reached.add(above)
                    pending.append(above)
        total += len(reached)
    return total / len(modules) ** 2
