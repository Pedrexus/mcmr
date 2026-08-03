from typing import TYPE_CHECKING

from ...foundation import Fact

if TYPE_CHECKING:
    from .definition import AlertDefinition


class AlertFact(Fact):
    """Describe operational alert definitions without judging actionability."""

    alerts: list[AlertDefinition] = []
