from patos import FrozenModel
from pydantic import NonNegativeFloat

from ....domain.primitives import NonEmptyStr


class PerformanceBudgetFields(FrozenModel):
    """Retain budget identity, limit, unit, workload, environment, and baseline."""

    name: NonEmptyStr
    critical: bool = True
    limit: NonNegativeFloat | None = None
    unit: str = ""
    workload: str = ""
    environment: str = ""
    baseline: str = ""
