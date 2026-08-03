from abc import ABC, abstractmethod

from patos import FrozenModel

from ..source import SourceKind


class CitedSource(FrozenModel, ABC):
    """Carry the display details shared by works and influence rows."""

    author: str = ""
    kind: SourceKind
    link: str = ""

    @property
    def citation(self) -> str:
        """Return this source as a page cites it, its name first and author behind it."""
        return f"{self.citation_title}, {self.author}" if self.author else self.citation_title

    @property
    @abstractmethod
    def citation_title(self) -> str:
        """Return the title or tool name that identifies this source."""
