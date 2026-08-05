import json
from collections.abc import Mapping, Sequence
from enum import StrEnum, auto
from pathlib import PurePosixPath

from patos import FrozenModel
from pydantic import Field, JsonValue, TypeAdapter, field_validator

from ...domain.contracts import Criterion, ModelProvenance
from ...domain.primitives import EvidenceIds, NonEmptyStr
from ...facts import Evidence

type DecisionTable[Category: StrEnum] = Sequence[tuple[Category, Sequence[tuple[str, StrEnum]]]]


class _ModelContracts:
    """Own model answers and their isolated transport payloads."""

    class ModelMode(StrEnum):
        """Name the two closed model operations MCMR can execute over candidates."""

        CLASSIFY = auto()
        ASSESS = auto()

    class AssessmentContract[Category: StrEnum](FrozenModel):
        """Own one cited assessment rubric and its deterministic reduction."""

        criteria: list[Criterion]
        instructions: str
        decision_table: DecisionTable[Category]
        default: Category
        uncertain: Category

        @field_validator("criteria")
        @classmethod
        def unique_criteria(cls, criteria: list[Criterion]) -> list[Criterion]:
            """Require criterion names to be unambiguous within one rubric."""
            if not criteria:
                raise ValueError("a model assessment needs at least one criterion")
            names = [criterion.name for criterion in criteria]
            if len(names) != len(set(names)):
                raise ValueError("model assessment criterion names must be unique")
            return criteria

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
        value: _ModelContracts.CriterionValue
        reasoning: NonEmptyStr = Field(max_length=500)
        evidence: EvidenceIds
        confidence: float = Field(ge=0.0, le=1.0)
        provenance: ModelProvenance

    class Assessment(FrozenModel):
        """Retain independent answers a deterministic decision table consumes."""

        answers: list[_ModelContracts.CriterionAnswer]

        def value(self, criterion: str) -> _ModelContracts.CriterionValue:
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

        value: _ModelContracts.CriterionValue
        reasoning: NonEmptyStr = Field(max_length=500)
        evidence_ids: EvidenceIds
        confidence: float = Field(ge=0.0, le=1.0)

    class AssessmentPayload(FrozenModel):
        """Validate one independent-criteria document returned by a model."""

        criteria: dict[NonEmptyStr, _ModelContracts.CriterionPayload]

    class ModelCandidate(FrozenModel):
        """Carry one normalized fact payload without rebuilding its Pydantic model."""

        fact_id: str
        path: str
        subject: JsonValue
        evidence: list[Evidence]

        @property
        def prompt_subject(self) -> JsonValue:
            """Replace separately cited records with their IDs when all are retained."""
            if not isinstance(self.subject, Mapping):
                return self.subject
            records = self.subject.get("records")
            if not isinstance(records, Sequence) or isinstance(records, str):
                return self.subject
            identifiers = [
                record.get("record_id")
                for record in records
                if isinstance(record, Mapping) and isinstance(record.get("record_id"), str)
            ]
            if not identifiers or not set(identifiers).issubset(self.retained):
                return self.subject
            return TypeAdapter(JsonValue).validate_python({**self.subject, "records": identifiers})

        @property
        def retained(self) -> dict[str, Evidence]:
            """Index every supplied claim by the exact citation ID a model may return."""
            return {claim.signal: claim for claim in self.evidence}

        @staticmethod
        def normalized_evidence(
            fact_id: str,
            *,
            path: str,
            subject: JsonValue,
        ) -> list[Evidence]:
            """Turn one normalized fact and its records into precise citable claims."""
            fields: JsonValue = subject
            records: JsonValue = None
            if isinstance(subject, Mapping):
                mapping = TypeAdapter(dict[str, JsonValue]).validate_python(subject)
                fields = mapping.get("fields", {})
                records = mapping.get("records")
            claims = [
                Evidence(
                    signal=f"fact:{fact_id}",
                    detail=json.dumps(fields, sort_keys=True),
                    source=PurePosixPath(path).as_posix(),
                )
            ]
            if not isinstance(records, list):
                return claims
            claims.extend(
                claim
                for raw in records
                if (claim := _ModelContracts.ModelCandidate.record_evidence(raw, path=path))
                is not None
            )
            return claims

        @staticmethod
        def record_evidence(raw: JsonValue, *, path: str) -> Evidence | None:
            """Turn one normalized record into a cited claim when it has an identity."""
            if not isinstance(raw, dict):
                return None
            record = TypeAdapter(dict[str, JsonValue]).validate_python(raw)
            identifier = record.get("record_id")
            if not isinstance(identifier, str) or not identifier.strip():
                return None
            detail = {
                name: value
                for name, value in record.items()
                if name not in {"record_id", "parent_id", "ordinal"} and value is not None
            }
            return Evidence(
                signal=identifier,
                detail=json.dumps(detail, sort_keys=True),
                source=PurePosixPath(path).as_posix(),
            )

        @classmethod
        def from_row(cls, row: Mapping[str, JsonValue]) -> _ModelContracts.ModelCandidate:
            """Validate the compact Polars transport row at the model boundary."""
            fact_id = TypeAdapter(str).validate_python(row["fact_id"])
            path = TypeAdapter(str).validate_python(row["path"])
            subject_json = TypeAdapter(str).validate_python(row["subject_json"])
            subject: JsonValue = TypeAdapter(JsonValue).validate_json(subject_json)
            supplied = row.get("evidence")
            evidence = (
                TypeAdapter(list[Evidence]).validate_python(supplied)
                if supplied is not None
                else []
            )
            if not evidence:
                evidence = cls.normalized_evidence(fact_id, path=path, subject=subject)
            return cls(fact_id=fact_id, path=path, subject=subject, evidence=evidence)


Assessment = _ModelContracts.Assessment
AssessmentContract = _ModelContracts.AssessmentContract
AssessmentPayload = _ModelContracts.AssessmentPayload
Classification = _ModelContracts.Classification
ClassificationPayload = _ModelContracts.ClassificationPayload
CriterionAnswer = _ModelContracts.CriterionAnswer
CriterionValue = _ModelContracts.CriterionValue
ModelCandidate = _ModelContracts.ModelCandidate
ModelMode = _ModelContracts.ModelMode
