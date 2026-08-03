from typing import TYPE_CHECKING

from ...foundation import Fact

if TYPE_CHECKING:
    from pydantic import NonNegativeInt

    from .candidate import SetLoopCandidate


class ComprehensionFact(Fact):
    """Describe one comprehension and its nested clauses."""

    loop_counts: list[NonNegativeInt] = []
    set_loop_candidates: list[SetLoopCandidate] = []
