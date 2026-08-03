from patos import FrozenModel

from ...reports.data.report import CheckReport
from ..contracts import FixRefusal, RenderedFix


class FixResult(FrozenModel):
    """Return the final judgment beside every applied and refused fix."""

    report: CheckReport
    applied: list[RenderedFix] = []
    refused: list[FixRefusal] = []
