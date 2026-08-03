from enum import StrEnum, auto
from typing import TYPE_CHECKING

from ...projections import JsonRendering, Rendering
from .text import SimulationText

if TYPE_CHECKING:
    from ..models import Simulation


class SimulationFormat(StrEnum):
    """Say whether a simulation is rendered for a person or another tool."""

    TEXT = auto()
    JSON = auto()

    def simulation(self, limit: int) -> Rendering[Simulation]:
        """Return the rendering a simulation takes in this format."""
        return SimulationText(limit=limit) if self is SimulationFormat.TEXT else JsonRendering()
