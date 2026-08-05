from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mcmr.domain.contracts import Criterion
    from mcmr.execution import (
        Assessment,
        ModelCandidate,
    )

from .labeled import LabeledBackend


class EmptyAssessmentBackend(LabeledBackend):
    """Return the wrong assessment cardinality for experiment failure coverage."""

    async def assess_many(
        self,
        candidates: Sequence[ModelCandidate],
        *,
        criteria: Sequence[Criterion],
        instructions: str,
    ) -> list[Assessment]:
        assert candidates and criteria and instructions
        return []
