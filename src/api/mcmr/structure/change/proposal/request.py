from typing import TYPE_CHECKING

from patos import FrozenModel

from ...projections import Dependency, ModuleGraph
from ..metrics import propagation
from ..models import AppliedChange, ProposedImport, Simulation

if TYPE_CHECKING:
    from collections.abc import Container, Iterable, Sequence


class ImportProposal(FrozenModel):
    """Ask what the import graph would become after a proposed change without editing files."""

    graph: ModuleGraph
    added: list[ProposedImport] = []
    removed: list[ProposedImport] = []

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
        return ModuleGraph(root=self.graph.root, paths=self.graph.paths, dependencies=ordered)

    def resolve(self) -> AppliedChange:
        """Classify every proposal as applied, unchanged, cancelled, or unknown."""
        named = set(self.graph.paths)
        present = {(item.importer, item.imported) for item in self.graph.dependencies}
        adding = self._pairs(self.added, named)
        removing = self._pairs(self.removed, named)
        return AppliedChange(
            added=self._proposals(sorted(adding - removing - present)),
            removed=self._proposals(sorted((removing - adding) & present)),
            unchanged=self._proposals(
                sorted(((adding - removing) & present) | ((removing - adding) - present))
            ),
            cancelled=self._proposals(sorted(adding & removing)),
            unknown=self._unknown(named),
        )

    def run(self) -> Simulation:
        """Apply what the graph can apply and report what the repository would become."""
        applied = self.resolve()
        hypothetical = self.hypothetical(applied)
        before, after = self.graph.matrix(), hypothetical.matrix()
        known = [set(cycle.members) for cycle in before.cycles]
        proposed = [set(cycle.members) for cycle in after.cycles]
        return Simulation(
            applied=applied,
            cycles_formed=[cycle for cycle in after.cycles if set(cycle.members) not in known],
            cycles_broken=[cycle for cycle in before.cycles if set(cycle.members) not in proposed],
            back_edges_formed=self._arriving(after.back_edges, against=before.back_edges),
            back_edges_cleared=self._arriving(before.back_edges, against=after.back_edges),
            propagation_before=propagation(self.graph),
            propagation_after=propagation(hypothetical),
        )

    @staticmethod
    def _arriving(
        subject: Sequence[Dependency],
        *,
        against: Sequence[Dependency],
    ) -> list[Dependency]:
        held = {(item.importer, item.imported) for item in against}
        return [item for item in subject if (item.importer, item.imported) not in held]

    @staticmethod
    def _pairs(
        items: Sequence[ProposedImport],
        named: Container[str],
    ) -> set[tuple[str, str]]:
        return {
            (item.importer, item.imported)
            for item in items
            if item.importer in named and item.imported in named
        }

    @staticmethod
    def _proposals(named: Iterable[tuple[str, str]]) -> list[ProposedImport]:
        return [
            ProposedImport(importer=importer, imported=imported) for importer, imported in named
        ]

    def _unknown(self, named: Container[str]) -> list[str]:
        return sorted(
            {
                name
                for item in (*self.added, *self.removed)
                for name in (item.importer, item.imported)
                if name not in named
            }
        )
