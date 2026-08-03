from typing import TYPE_CHECKING

from ....foundation import Fact

if TYPE_CHECKING:
    from .trigger import RunbookTrigger


class RunbookFact(Fact):
    """Describe operational triggers and their linked procedures."""

    triggers: list[RunbookTrigger] = []
