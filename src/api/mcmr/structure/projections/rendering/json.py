from patos import FrozenModel
from pydantic import NonNegativeInt


class JsonRendering(FrozenModel):
    """Render any frozen projection as structured JSON."""

    indent: NonNegativeInt = 2

    def render(self, projection: FrozenModel) -> str:
        """Return the projection as indented JSON."""
        return projection.model_dump_json(indent=self.indent)
