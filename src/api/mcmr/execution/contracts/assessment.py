from enum import StrEnum, auto

from patos import FrozenModel
from pydantic import Field

from ...domain.contracts import ModelProvenance
from ...domain.primitives import EvidenceIds, NonEmptyStr


class _AssessmentContracts:
    """Own model answers and their isolated transport payloads."""

    class Classification[Category: StrEnum](FrozenModel):
        """Retain one closed model answer and the claims needed to audit it."""

        value: Category
        reasoning: NonEmptyStr = Field(max_length=500)
        evidence: EvidenceIds
        confidence: float = Field(ge=0.0, le=1.0)
        provenance: ModelProvenance

    class CriterionValue(StrEnum):
        """State whether retained evidence establishes one predicate."""

        YES = auto()
        NO = auto()
        UNKNOWN = auto()

    class CriterionAnswer(FrozenModel):
        """Retain one cited predicate answer from a model assessment."""

        criterion: NonEmptyStr
        value: _AssessmentContracts.CriterionValue
        reasoning: NonEmptyStr = Field(max_length=500)
        evidence: EvidenceIds
        confidence: float = Field(ge=0.0, le=1.0)
        provenance: ModelProvenance

    class Assessment(FrozenModel):
        """Retain independent answers a deterministic decision table consumes."""

        answers: list[_AssessmentContracts.CriterionAnswer]

        def value(self, criterion: str) -> _AssessmentContracts.CriterionValue:
            """Return one named answer whose presence the backend already proved."""
            return next(answer.value for answer in self.answers if answer.criterion == criterion)

    class ClassificationPayload(FrozenModel):
        """Validate the one JSON document an isolated model process returns."""

        category: NonEmptyStr
        reasoning: NonEmptyStr = Field(max_length=500)
        evidence_ids: EvidenceIds
        confidence: float = Field(ge=0.0, le=1.0)

    class CriterionPayload(FrozenModel):
        """Validate one criterion returned by an isolated model process."""

        value: _AssessmentContracts.CriterionValue
        reasoning: NonEmptyStr = Field(max_length=500)
        evidence_ids: EvidenceIds
        confidence: float = Field(ge=0.0, le=1.0)

    class AssessmentPayload(FrozenModel):
        """Validate one independent-criteria document returned by a model."""

        criteria: dict[NonEmptyStr, _AssessmentContracts.CriterionPayload]


Assessment = _AssessmentContracts.Assessment
AssessmentPayload = _AssessmentContracts.AssessmentPayload
Classification = _AssessmentContracts.Classification
ClassificationPayload = _AssessmentContracts.ClassificationPayload
CriterionAnswer = _AssessmentContracts.CriterionAnswer
CriterionValue = _AssessmentContracts.CriterionValue
