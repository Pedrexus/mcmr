from typing import TYPE_CHECKING

from ...foundation import Fact

if TYPE_CHECKING:
    from .usage import ExceptionUsage


class ExceptionFact(Fact):
    """Describe one exception declaration and its uses."""

    exceptions: list[ExceptionUsage] = []
