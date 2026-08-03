from patos import FrozenModel

from .....domain.primitives import NonEmptyStr
from ..state import ReplacementState


class CapabilityReplacement(FrozenModel):
    """State the supported successor or the explicit reason a behavior is gone."""

    source_id: NonEmptyStr
    state: ReplacementState
    replacement: NonEmptyStr
    reason: NonEmptyStr
