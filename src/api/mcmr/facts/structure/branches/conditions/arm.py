from patos import FrozenModel
from pydantic import NonNegativeInt


class ConditionalArm(FrozenModel):
    """Retain one conditional arm and its selecting comparison."""

    comparison: str = ""
    literal: str = ""
    statement_count: NonNegativeInt = 0
    returns_value: bool = False
    reads_subject_only: bool = True
