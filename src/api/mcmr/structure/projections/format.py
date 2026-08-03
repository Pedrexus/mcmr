from enum import StrEnum, auto
from typing import TYPE_CHECKING

from .rendering import ImpactText, JsonRendering, MatrixText

if TYPE_CHECKING:
    from .contracts import Rendering
    from .impacts import ImpactSet
    from .matrices import DesignStructureMatrix


class ProjectionFormat(StrEnum):
    """Choose human-readable or structured projection rendering."""

    TEXT = auto()
    JSON = auto()

    def impact(self) -> Rendering[ImpactSet]:
        """Return the impact renderer for this format."""
        return ImpactText() if self is ProjectionFormat.TEXT else JsonRendering()

    def matrix(self, limit: int) -> Rendering[DesignStructureMatrix]:
        """Return the matrix renderer for this format."""
        return MatrixText(limit=limit) if self is ProjectionFormat.TEXT else JsonRendering()
