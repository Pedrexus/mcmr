from patos import FrozenModel
from pydantic import NonNegativeInt

from ....domain.primitives import NonEmptyStr


class FeatureFlag(FrozenModel):
    """Retain one flag's dates, role, ownership, states, and cleanup plan."""

    name: NonEmptyStr
    age_days: NonNegativeInt
    role: str = ""
    owner: str = ""
    tested_states: list[str] = []
    decision_due_days: int | None = None
    cleanup_plan: str = ""
