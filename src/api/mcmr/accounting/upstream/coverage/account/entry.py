from patos import FrozenModel

from ....inventory.contracts import ToolRule
from ...profiles.coverage import Coverage


class CoverageEntry(FrozenModel):
    """State what MCMR does about one rule of one upstream tool and why."""

    rule: ToolRule
    coverage: Coverage
    reason: str
    rules: list[str] = []
