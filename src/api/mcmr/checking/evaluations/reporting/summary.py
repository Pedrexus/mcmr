from patos import FrozenModel
from pydantic import NonNegativeInt


class TableRuleSummary(FrozenModel):
    """Hold one table rule's repository-wide judgment totals."""

    rule: str
    observation_count: NonNegativeInt
    unassessed_count: NonNegativeInt
    failure_count: NonNegativeInt
    finding_count: NonNegativeInt
