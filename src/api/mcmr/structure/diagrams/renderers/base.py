from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from patos import Registry

if TYPE_CHECKING:
    from typing import ClassVar

    from ..kinds import DiagramFormat
    from ..models import Diagram


class DiagramRenderer(Registry, ABC):
    """Render one notation from a notation-independent diagram."""

    notation: ClassVar[DiagramFormat]

    @classmethod
    def of(cls, notation: DiagramFormat) -> DiagramRenderer:
        """Return the renderer registered for one notation."""
        return cls.find(notation, attr="notation")()

    @abstractmethod
    def render(self, diagram: Diagram) -> str:
        """Return the complete diagram in this notation."""
