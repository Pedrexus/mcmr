from patos import FrozenModel
from pydantic import PositiveInt

from ...foundation import SourceSpan


class RouteReference(FrozenModel):
    """Retain one literal reference to a route path."""

    path: str
    language: str
    line: PositiveInt = 1

    @property
    def span(self) -> SourceSpan:
        """Locate this literal reference in its source file."""
        return SourceSpan(path=self.path, start_line=self.line)
