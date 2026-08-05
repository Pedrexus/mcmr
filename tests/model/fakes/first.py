from enum import StrEnum

from mcmr.domain.contracts import ModelProvenance
from mcmr.execution import (
    Classification,
    ClassificationBackend,
    ModelCandidate,
)


class FirstCategoryBackend(ClassificationBackend):
    """Return the first closed answer while preserving normal provenance."""

    async def classify_candidate[Category: StrEnum](
        self,
        candidate: ModelCandidate,
        *,
        category: type[Category],
        instructions: str,
    ) -> Classification[Category]:
        assert instructions
        return Classification(
            value=next(iter(category)),
            reasoning="Controlled classification for contract verification.",
            evidence=list(candidate.retained)[:8],
            confidence=1.0,
            provenance=ModelProvenance(
                backend="controlled", model="test", reasoning_effort="none"
            ),
        )
