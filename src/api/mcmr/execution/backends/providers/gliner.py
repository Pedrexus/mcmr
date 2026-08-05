import asyncio
import json
from enum import StrEnum
from functools import cached_property, partial
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from pydantic import Field, JsonValue, PositiveInt, TypeAdapter

from ....domain import primitives
from ....domain.contracts import Criterion, ModelProvenance
from ....kernel_tables import GlinerClassifier
from ...queries.contracts import (
    Assessment,
    Classification,
    CriterionAnswer,
    CriterionValue,
    ModelCandidate,
)
from ...queries.runtime import ClassificationBackend

if TYPE_CHECKING:
    from collections.abc import Sequence


class Gliner2Backend(ClassificationBackend):
    """Batch closed contextual classifications through the native GLiNER2 runtime."""

    name: ClassVar[str] = "gliner2"
    model: primitives.NonEmptyStr = "fastino/gliner2-base-v1"
    model_path: Path | None = None
    minimum_confidence: float = Field(default=0.6, ge=0.0, le=1.0)
    batch_size: PositiveInt = 8

    @cached_property
    def classifier(self) -> GlinerClassifier:
        """Load explicitly provisioned model weights once for this process."""
        if self.model_path is None:
            raise ValueError("GLiNER2 needs tool.mcmr.contextual.model_path")
        return GlinerClassifier(self.model_path)

    @staticmethod
    def text(candidate: ModelCandidate, instructions: str) -> str:
        """Render the rule rubric and structured candidate as classification text."""
        return (
            f"Software engineering rubric\n{instructions.strip()}\n\n"
            f"Subject\n{json.dumps(candidate.subject, sort_keys=True)}\n\n"
            "Evidence\n"
            + json.dumps(
                [
                    {
                        "id": identifier,
                        "detail": evidence.detail,
                        "source": evidence.source,
                    }
                    for identifier, evidence in candidate.retained.items()
                ],
                sort_keys=True,
            )
        )

    async def assess_many(
        self,
        candidates: Sequence[ModelCandidate],
        *,
        criteria: Sequence[Criterion],
        instructions: str,
    ) -> Sequence[Assessment]:
        """Batch every independent criterion across all candidates."""
        answers: list[list[CriterionAnswer]] = [[] for _ in candidates]
        for criterion in criteria:
            classified = await self.classify_many(
                candidates,
                category=CriterionValue,
                instructions=f"{instructions}\n\nAssess only this criterion. {criterion.question}",
            )
            for held, answer in zip(answers, classified, strict=True):
                held.append(
                    CriterionAnswer(
                        criterion=criterion.name,
                        value=answer.value,
                        reasoning=answer.reasoning,
                        evidence=answer.evidence,
                        confidence=answer.confidence,
                        provenance=answer.provenance,
                    )
                )
        return [Assessment(answers=held) for held in answers]

    async def classify_candidate[Category: StrEnum](
        self,
        candidate: ModelCandidate,
        *,
        category: type[Category],
        instructions: str,
    ) -> Classification[Category]:
        """Retain the scalar interface for direct backend contract tests."""
        outcomes = await self.classify_many(
            [candidate], category=category, instructions=instructions
        )
        return outcomes[0]

    async def classify_many[Category: StrEnum](
        self,
        candidates: Sequence[ModelCandidate],
        *,
        category: type[Category],
        instructions: str,
    ) -> Sequence[Classification[Category]]:
        """Classify one complete candidate batch with a single native model call."""
        if not candidates:
            return []
        texts = [self.text(candidate, instructions) for candidate in candidates]
        labels = json.dumps(
            {str(value): value.name.lower().replace("_", " ") for value in category},
            sort_keys=True,
        )
        source = await asyncio.to_thread(
            partial(
                self.classifier.classify,
                texts,
                "classification",
                labels=labels,
                batch_size=self.batch_size,
            )
        )
        payloads = TypeAdapter(list[dict[str, JsonValue]]).validate_json(source)
        if len(payloads) != len(candidates):
            raise ValueError("GLiNER2 returned a different number of classifications")
        uncertain = next((value for value in category if str(value) == "uncertain"), None)
        outcomes: list[Classification[Category]] = []
        for candidate, payload in zip(candidates, payloads, strict=True):
            answer = TypeAdapter(dict[str, JsonValue]).validate_python(
                payload.get("classification")
            )
            label = TypeAdapter(str).validate_python(answer.get("label"))
            confidence = TypeAdapter(float).validate_python(answer.get("confidence"))
            value = category(label)
            if confidence < self.minimum_confidence and uncertain is not None:
                value = uncertain
            evidence = next(iter(candidate.retained))
            outcomes.append(
                Classification(
                    value=value,
                    reasoning=f"GLiNER2 selected {label} from the closed rule categories.",
                    evidence=[evidence],
                    confidence=confidence,
                    provenance=ModelProvenance(
                        backend=self.name,
                        model=self.model,
                        reasoning_effort="none",
                    ),
                )
            )
        return outcomes


Gliner2Backend.model_rebuild(_types_namespace={"primitives": primitives})
