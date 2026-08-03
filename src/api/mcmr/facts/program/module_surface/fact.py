from typing import TYPE_CHECKING

from pydantic import NonNegativeInt, model_validator

from .groups import ModuleSurfaceFields

if TYPE_CHECKING:
    from typing import Self

    from .types import ModuleSurfaceTypes


class ModuleSurfaceFact(ModuleSurfaceFields):
    """Describe what one module publishes and its type-system escape hatches."""

    escape_hatches: list[ModuleSurfaceTypes.EscapeHatch] = []
    physical_line_count: NonNegativeInt = 0

    @model_validator(mode="after")
    def fit_inside_module(self) -> Self:
        """Require every escape hatch to fit inside the measured module."""
        if len(self.escape_hatches) > self.physical_line_count:
            raise ValueError(
                f"module holds {len(self.escape_hatches)} escape hatches inside "
                f"{self.physical_line_count} physical lines"
            )
        if any(hatch.line > self.physical_line_count for hatch in self.escape_hatches):
            raise ValueError("module holds an escape hatch beyond its physical lines")
        return self
