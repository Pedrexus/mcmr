from typing import TYPE_CHECKING

from .groups import TestStrategyFields

if TYPE_CHECKING:
    from ...foundation import Ratio


class TestStrategyFact(TestStrategyFields):
    """Describe test strategy evidence without deciding whether it is sufficient."""

    mutation_score: Ratio | None = None
