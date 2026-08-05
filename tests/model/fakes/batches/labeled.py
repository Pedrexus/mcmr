from enum import StrEnum
from typing import TYPE_CHECKING

from mcmr.domain.contracts import ModelProvenance
from mcmr.execution import (
    Assessment,
    Classification,
    ClassificationBackend,
    CriterionAnswer,
    CriterionValue,
    ModelCandidate,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mcmr.domain.contracts import Criterion


class LabeledBackend(ClassificationBackend):
    """Return configured labels for contextual experiment tests."""

    classification_value: str

    async def assess_candidate(
        self,
        candidate: ModelCandidate,
        *,
        criteria: Sequence[Criterion],
        instructions: str,
    ) -> Assessment:
        return Assessment(
            answers=[
                CriterionAnswer(
                    criterion=criterion.name,
                    value=CriterionValue.YES,
                    reasoning=instructions,
                    evidence=list(candidate.retained),
                    confidence=1.0,
                    provenance=ModelProvenance(
                        backend="controlled", model="test", reasoning_effort="none"
                    ),
                )
                for criterion in criteria
            ]
        )

    async def classify_candidate[Category: StrEnum](
        self,
        candidate: ModelCandidate,
        *,
        category: type[Category],
        instructions: str,
    ) -> Classification[Category]:
        return Classification(
            value=category(self.classification_value),
            reasoning=instructions,
            evidence=list(candidate.retained),
            confidence=1.0,
            provenance=ModelProvenance(
                backend="controlled", model="test", reasoning_effort="none"
            ),
        )
