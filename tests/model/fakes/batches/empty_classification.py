from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mcmr.execution import (
        Classification,
        ModelCandidate,
    )


from .labeled import LabeledBackend


class EmptyBatchBackend(LabeledBackend):
    """Return the wrong cardinality so the experiment retains one backend failure."""

    async def classify_many[Category: StrEnum](
        self,
        candidates: Sequence[ModelCandidate],
        *,
        category: type[Category],
        instructions: str,
    ) -> list[Classification[Category]]:
        assert candidates and category and instructions
        return []
