from typing import TYPE_CHECKING

from ...foundation import Fact

if TYPE_CHECKING:
    from .budget import PerformanceBudget


class PerformanceDecisionFact(Fact):
    """Describe declared performance budgets and repeatable check inputs."""

    budgets: list[PerformanceBudget] = []
