from enum import StrEnum, auto
from typing import TYPE_CHECKING

from patos import FrozenModel
from pydantic import NonNegativeInt

from .renderers import ConciseText, FullText

if TYPE_CHECKING:
    from ..data.report.check import CheckReport
    from .base import CheckRendering


class _CheckFormats:
    """Own the format selector and its machine-readable renderer."""

    class JsonCheck(FrozenModel):
        """Render the complete check contract as deterministic JSON."""

        indent: NonNegativeInt = 2

        def render(self, projection: CheckReport) -> str:
            """Return every retained failure and aggregate without decoration."""
            return projection.model_dump_json(indent=self.indent)

    class CheckFormat(StrEnum):
        """Say which register prints a check for a reader or program."""

        RICH = auto()
        FULL = auto()
        CONCISE = auto()
        JSON = auto()

        def check(self, limit: int) -> CheckRendering | JsonCheck:
            """Return the stable rendering requested by a non-Rich register."""
            if self is CheckFormat.JSON:
                return JsonCheck()
            return FullText(limit=limit) if self is CheckFormat.FULL else ConciseText(limit=limit)


CheckFormat = _CheckFormats.CheckFormat
JsonCheck = _CheckFormats.JsonCheck
