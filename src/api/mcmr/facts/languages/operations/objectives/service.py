from .groups import ServiceObjectiveFields


class ServiceObjective(ServiceObjectiveFields):
    """Retain one service and the fields required to operate its objective."""

    windows: list[str] = []
    error_budget_policy: str = ""
