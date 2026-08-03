from patos import FrozenModel

from ...primitives import FixSafety


class FixDefinition(FrozenModel):
    """Describe one validated fix attached to a catalog rule."""

    name: str
    callable: str
    is_default: bool
    safety: FixSafety
