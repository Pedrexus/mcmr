from .groups import AlertDefinitionFields


class AlertDefinition(AlertDefinitionFields):
    """Retain the configured fields one responder receives from an alert."""

    destination: str = ""
    action: str = ""
    runbook: str = ""
    recent_outcomes: list[str] = []
