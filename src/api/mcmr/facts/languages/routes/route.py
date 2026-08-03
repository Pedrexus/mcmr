from patos import FrozenModel
from pydantic import PositiveInt

from ...foundation import SourceSpan
from .reference import RouteReference


class Route(FrozenModel):
    """Retain one declared route and every literal naming its path."""

    method: str
    path: str
    framework: str
    declared_in: str
    line: PositiveInt = 1
    is_prefix_composed: bool = False
    references: list[RouteReference] = []

    @property
    def span(self) -> SourceSpan:
        """Locate this route where its framework declares it."""
        return SourceSpan(path=self.declared_in, start_line=self.line)
