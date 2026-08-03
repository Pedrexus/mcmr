import asyncio
from abc import ABC, abstractmethod
from enum import StrEnum
from typing import TYPE_CHECKING, cast

from patos import Component
from pydantic import JsonValue, PositiveInt

from ....domain.contracts import Criterion, ModelProvenance
from ....domain.primitives import NonEmptyStr
from ....facts import Fact
from ...contracts import (
    Assessment,
    Classification,
    CriterionAnswer,
    CriterionValue,
    ModelCandidate,
)
from ..definitions import ModelMode
from ..model import ModelQuery
from .answers import answer_frame

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ....domain.contracts import RuleValue
    from ....query import RuleQuery
    from ....table import Table
    from ..assessment.contract import AssessmentContract


class ClassificationBackend(Component, ABC):
    """Classify primitive evidence against one explicit closed rubric."""

    workers: PositiveInt = 8
    model: NonEmptyStr = "unknown"
    reasoning_effort: NonEmptyStr = "none"

    async def assess_candidate(
        self,
        candidate: ModelCandidate,
        *,
        criteria: Sequence[Criterion],
        instructions: str,
    ) -> Assessment:
        """Assess one normalized candidate inside a batch backend implementation."""
        answers = []
        for criterion in criteria:
            classification = await self.classify_candidate(
                candidate,
                category=CriterionValue,
                instructions=f"{instructions}\n\nAssess only this criterion. {criterion.question}",
            )
            answers.append(
                CriterionAnswer(
                    criterion=criterion.name,
                    value=classification.value,
                    reasoning=classification.reasoning,
                    evidence=classification.evidence,
                    confidence=classification.confidence,
                    provenance=classification.provenance,
                )
            )
        return Assessment(answers=answers)

    async def assess_many(
        self,
        candidates: Sequence[ModelCandidate],
        *,
        criteria: Sequence[Criterion],
        instructions: str,
    ) -> Sequence[Assessment]:
        """Assess candidates concurrently when a backend has no native batch operation."""
        limiter = asyncio.Semaphore(self.workers)

        async def execute(candidate: ModelCandidate) -> Assessment:
            async with limiter:
                try:
                    return await self.assess_candidate(
                        candidate, criteria=criteria, instructions=instructions
                    )
                except (OSError, RuntimeError, ValueError) as error:
                    return self._failed_assessment(candidate, criteria, error)

        return await asyncio.gather(*(execute(candidate) for candidate in candidates))

    def assessment[Family: Fact, Category: StrEnum](
        self,
        subjects: Table[Family],
        *,
        contract: AssessmentContract[Category],
    ) -> ModelQuery[Category]:
        """Plan one cited predicate batch followed by a deterministic reducer."""
        return ModelQuery.assess(subjects, contract=contract)

    def classification[Family: Fact, Category: StrEnum](
        self,
        subjects: Table[Family],
        *,
        category: type[Category],
        instructions: str,
    ) -> ModelQuery[Category]:
        """Plan one closed classification over a complete typed fact table."""
        return ModelQuery.classify(subjects, category=category, instructions=instructions)

    @abstractmethod
    async def classify_candidate[Category: StrEnum](
        self,
        candidate: ModelCandidate,
        *,
        category: type[Category],
        instructions: str,
    ) -> Classification[Category]:
        """Classify one normalized candidate inside a batch backend implementation."""
        raise NotImplementedError

    async def classify_many[Category: StrEnum](
        self,
        candidates: Sequence[ModelCandidate],
        *,
        category: type[Category],
        instructions: str,
    ) -> Sequence[Classification[Category]]:
        """Classify candidates concurrently when a backend has no native batch operation."""
        limiter = asyncio.Semaphore(self.workers)

        async def execute(candidate: ModelCandidate) -> Classification[Category]:
            async with limiter:
                try:
                    return await self.classify_candidate(
                        candidate, category=category, instructions=instructions
                    )
                except (OSError, RuntimeError, ValueError) as error:
                    return self._failed_classification(candidate, category, error)

        return await asyncio.gather(*(execute(candidate) for candidate in candidates))

    async def resolve[Category: StrEnum](
        self,
        query: ModelQuery[Category],
    ) -> RuleQuery[RuleValue]:
        """Execute one batched backend request and return normalized relational answers."""
        candidate_frame = query.candidates.collect()
        rows = cast("list[dict[str, JsonValue]]", candidate_frame.to_dicts())
        candidates = [ModelCandidate.from_row(row) for row in rows]
        outcomes: Sequence[Classification[StrEnum] | Assessment]
        if query.mode is ModelMode.CLASSIFY:
            outcomes = await self.classify_many(
                candidates, category=query.category, instructions=query.instructions
            )
        else:
            outcomes = await self.assess_many(
                candidates, criteria=query.criteria, instructions=query.instructions
            )
        answers = answer_frame(query, rows=rows, outcomes=outcomes)
        return query.resolved(candidate_frame, answers=answers)

    def unreported_provenance(self) -> ModelProvenance:
        """Describe this backend when a failed turn supplied no usable telemetry."""
        return ModelProvenance(
            backend=self.name,
            model=self.model,
            reasoning_effort=self.reasoning_effort,
        )

    @staticmethod
    def _failure_reason(error: OSError | RuntimeError | ValueError) -> str:
        """Describe one isolated backend failure within the model reasoning bound."""
        reason = f"Backend response was unusable because {type(error).__name__} reported {error}"
        return reason[:500]

    def _failed_assessment(
        self,
        candidate: ModelCandidate,
        criteria: Sequence[Criterion],
        error: OSError | RuntimeError | ValueError,
    ) -> Assessment:
        """Turn one unusable response into explicit unknown predicate answers."""
        evidence = [next(iter(candidate.retained))]
        reasoning = self._failure_reason(error)
        provenance = self.unreported_provenance()
        return Assessment(
            answers=[
                CriterionAnswer(
                    criterion=criterion.name,
                    value=CriterionValue.UNKNOWN,
                    reasoning=reasoning,
                    evidence=evidence,
                    confidence=0.0,
                    provenance=provenance,
                )
                for criterion in criteria
            ]
        )

    def _failed_classification[Category: StrEnum](
        self,
        candidate: ModelCandidate,
        category: type[Category],
        error: OSError | RuntimeError | ValueError,
    ) -> Classification[Category]:
        """Turn one unusable response into an explicit uncertain classification."""
        uncertain = next((value for value in category if str(value) == "uncertain"), None)
        if uncertain is None:
            raise error
        return Classification(
            value=uncertain,
            reasoning=self._failure_reason(error),
            evidence=[next(iter(candidate.retained))],
            confidence=0.0,
            provenance=self.unreported_provenance(),
        )
