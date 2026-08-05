from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mcmr.domain.contracts import Criterion
    from mcmr.execution import (
        Assessment,
        Classification,
        ModelCandidate,
    )

from ..batches.labeled import LabeledBackend


class FailingBatchBackend(LabeledBackend):
    """Raise one bounded backend failure from either native batch lane."""

    async def assess_many(
        self,
        candidates: Sequence[ModelCandidate],
        *,
        criteria: Sequence[Criterion],
        instructions: str,
    ) -> list[Assessment]:
        raise RuntimeError((candidates, criteria, instructions))

    async def classify_many[Category: StrEnum](
        self,
        candidates: Sequence[ModelCandidate],
        *,
        category: type[Category],
        instructions: str,
    ) -> list[Classification[Category]]:
        raise RuntimeError((candidates, category, instructions))
