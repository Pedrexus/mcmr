from .groups import PerformanceBudgetFields


class PerformanceBudget(PerformanceBudgetFields):
    """Retain one critical budget and the artifacts needed to repeat its check."""

    variance_policy: str = ""
    check_command: str = ""
    owner: str = ""
    last_outcome: str = ""
