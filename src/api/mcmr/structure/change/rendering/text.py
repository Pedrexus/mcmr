from typing import TYPE_CHECKING

from patos import FrozenModel
from pydantic import NonNegativeInt

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from ...projections import Dependency
    from ..models import Simulation


class SimulationText(FrozenModel):
    """Render what proposed imports would do to the shape of a repository."""

    limit: NonNegativeInt = 10

    def render(self, projection: Simulation) -> str:
        """State what was applied, then what it would form, break, and cost."""
        lines = self._header(projection)
        for title, entries in self._sections(projection).items():
            lines.extend(self._section(title, entries))
        return "\n".join(lines)

    @staticmethod
    def _back_edges(edges: Sequence[Dependency]) -> list[str]:
        return [f"{item.importer} imports {item.imported}" for item in edges]

    @staticmethod
    def _header(projection: Simulation) -> list[str]:
        applied = projection.applied
        moved = projection.propagation_after - projection.propagation_before
        return [
            f"{len(applied.added)} imports added and {len(applied.removed)} removed, "
            f"in the graph alone, with no file touched",
            "",
            f"propagation cost {projection.propagation_before:.4f} becomes "
            f"{projection.propagation_after:.4f} ({moved:+.4f})",
        ]

    @staticmethod
    def _sections(projection: Simulation) -> dict[str, list[str]]:
        applied = projection.applied
        return {
            "Added": [item.arrow() for item in applied.added],
            "Removed": [item.arrow() for item in applied.removed],
            "Already as asked": [item.arrow() for item in applied.unchanged],
            "Stated both ways": [item.arrow() for item in applied.cancelled],
            "Unknown modules": applied.unknown,
            "Cycles formed": [" ".join(cycle.members) for cycle in projection.cycles_formed],
            "Cycles broken": [" ".join(cycle.members) for cycle in projection.cycles_broken],
            "Back edges formed": SimulationText._back_edges(projection.back_edges_formed),
            "Back edges cleared": SimulationText._back_edges(projection.back_edges_cleared),
        }

    def _section(self, title: str, entries: Iterable[str]) -> list[str]:
        held = list(entries)
        shown = held[: self.limit]
        lines = ["", f"{title} ({len(held)})", *(f"  {entry}" for entry in shown)]
        if omitted := len(held) - len(shown):
            lines.append(f"  and {omitted} more")
        return lines
