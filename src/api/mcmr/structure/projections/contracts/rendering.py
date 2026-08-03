from typing import Protocol


class Rendering[Projection](Protocol):
    """Render one typed projection for a person or another tool."""

    def render(self, projection: Projection) -> str:
        """Return the complete projection as text."""
        ...
