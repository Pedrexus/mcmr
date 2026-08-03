import json
from collections.abc import Mapping, Sequence

from patos import FrozenModel
from pydantic import JsonValue, TypeAdapter

from ...facts import Evidence


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
                source=path,
            )
        ]
        if not isinstance(records, list):
            return claims
        claims.extend(
            claim
            for raw in records
            if (claim := ModelCandidate.record_evidence(raw, path=path)) is not None
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
            source=path,
        )

    @classmethod
    def from_row(cls, row: Mapping[str, JsonValue]) -> ModelCandidate:
        """Validate the compact Polars transport row at the model boundary."""
        fact_id = TypeAdapter(str).validate_python(row["fact_id"])
        path = TypeAdapter(str).validate_python(row["path"])
        subject_json = TypeAdapter(str).validate_python(row["subject_json"])
        subject: JsonValue = TypeAdapter(JsonValue).validate_json(subject_json)
        supplied = row.get("evidence")
        evidence = (
            TypeAdapter(list[Evidence]).validate_python(supplied) if supplied is not None else []
        )
        if not evidence:
            evidence = cls.normalized_evidence(fact_id, path=path, subject=subject)
        return cls(fact_id=fact_id, path=path, subject=subject, evidence=evidence)
