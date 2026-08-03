from patos import FrozenModel
from pydantic import NonNegativeInt


class Dependency(FrozenModel):
    """Hold one module import and every source line that states it."""

    importer: str
    imported: str
    path: str
    lines: list[NonNegativeInt] = []

    def location(self) -> str:
        """Return the file and lines that state this import."""
        return f"{self.path}:{','.join(str(line) for line in self.lines)}"
