from typing import TYPE_CHECKING

from ...foundation import Fact

if TYPE_CHECKING:
    from .task import AutomationTask


class AutomationTaskFact(Fact):
    """Describe one repeatable task and its automation entry point."""

    tasks: list[AutomationTask] = []
