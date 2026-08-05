from enum import StrEnum
from typing import TYPE_CHECKING

from ..first import FirstCategoryBackend

if TYPE_CHECKING:
    from mcmr.execution import (
        Classification,
        ModelCandidate,
    )


class PartlyFailingBackend(FirstCategoryBackend):
    """Reject only the candidate selected by one batch isolation test."""

    async def classify_candidate[Category: StrEnum](
        self,
        candidate: ModelCandidate,
        *,
        category: type[Category],
        instructions: str,
    ) -> Classification[Category]:
        if candidate.path == "broken.py":
            raise ValueError("model cited unknown evidence")
        return await super().classify_candidate(
            candidate,
            category=category,
            instructions=instructions,
        )
