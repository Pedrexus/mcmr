from patos import FrozenModel
from pydantic import NonNegativeFloat

from ....foundation import Ratio


class CICheck(FrozenModel):
    """Describe one CI check and its measured duration percentile."""

    name: str
    duration_percentile_seconds: NonNegativeFloat
    percentile: Ratio = 0.9
    is_required: bool = True
    is_change_blocking: bool = True
