from typing import TYPE_CHECKING

from patos import FrozenModel
from pydantic import PositiveInt

if TYPE_CHECKING:
    from collections.abc import Container, Sequence

    from ..matrices import DesignStructureMatrix


class MatrixText(FrozenModel):
    """Render a bounded design structure matrix and its backward edges."""

    limit: PositiveInt = 32

    def glyph(self, row: int, *, column: int, filled: Container[tuple[int, int]]) -> str:
        """Return the glyph for one matrix entry."""
        if row == column:
            return "\\"
        if (row, column) not in filled:
            return "."
        return "<" if row > column else "X"

    def grid(self, count: int, *, width: int, filled: set[tuple[int, int]]) -> list[str]:
        """Return the numbered matrix grid."""
        step = width + 1
        return [
            " " * width + "".join(f"{index + 1:>{step}}" for index in range(count)),
            *(
                f"{row + 1:>{width}}"
                + "".join(
                    f"{self.glyph(row, column=column, filled=filled):>{step}}"
                    for column in range(count)
                )
                for row in range(count)
            ),
        ]

    def heading(self, projection: DesignStructureMatrix, shown: Sequence[str]) -> list[str]:
        """Return the title and module legend."""
        width = len(str(len(shown)))
        return [
            f"Design structure matrix over {len(projection.ordering)} modules "
            f"and {len(projection.cells)} dependencies",
            "",
            *(f"{index + 1:>{width}} {module}" for index, module in enumerate(shown)),
            "",
        ]

    def render(self, projection: DesignStructureMatrix) -> str:
        """Draw the legend, grid, cycles, and dependencies pointing backwards."""
        shown = projection.ordering[: self.limit]
        width = len(str(len(shown)))
        filled = {(cell.row, cell.column) for cell in projection.cells}
        lines = self.heading(projection, shown) + self.grid(len(shown), width=width, filled=filled)
        lines += self.section("Cycles", [" ".join(cycle.members) for cycle in projection.cycles])
        lines += self.section(
            "Back edges",
            [
                f"{edge.importer} imports {edge.imported} at {edge.location()}"
                for edge in projection.back_edges
            ],
        )
        if omitted := len(projection.ordering) - len(shown):
            lines += ["", f"{omitted} more modules follow these in the ordering"]
        return "\n".join(lines)

    def section(self, title: str, entries: Sequence[str]) -> list[str]:
        """Return one bounded titled block beneath the grid."""
        shown = entries[: self.limit]
        omitted = len(entries) - len(shown)
        return [
            "",
            f"{title} ({len(entries)})",
            *(f"  {entry}" for entry in shown),
            *([f"  and {omitted} more"] if omitted else []),
        ]
