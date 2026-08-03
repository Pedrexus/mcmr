from enum import StrEnum
from typing import TYPE_CHECKING

import polars as pl
from pydantic import JsonValue, TypeAdapter

from ...contracts import Assessment, Classification
from ..definitions import ModelMode

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from ....domain.contracts import ModelProvenance
    from ..model import ModelQuery


def answer_frame[Category: StrEnum](
    query: ModelQuery[Category],
    *,
    rows: Sequence[Mapping[str, JsonValue]],
    outcomes: Sequence[Classification[StrEnum] | Assessment],
) -> pl.DataFrame:
    """Normalize typed model results into classification or criterion rows."""
    normalized: list[dict[str, JsonValue]] = []
    for row, outcome in zip(rows, outcomes, strict=True):
        fact_id = TypeAdapter(str).validate_python(row["fact_id"])
        if isinstance(outcome, Classification):
            classification = _provenance_columns(outcome.provenance)
            classification["fact_id"] = fact_id
            classification["answer_value"] = str(outcome.value)
            classification["reasoning"] = outcome.reasoning
            classification["evidence_ids"] = [str(identifier) for identifier in outcome.evidence]
            classification["confidence"] = outcome.confidence
            normalized.append(classification)
            continue
        for order, answer in enumerate(outcome.answers):
            criterion = _provenance_columns(answer.provenance)
            criterion["fact_id"] = fact_id
            criterion["criterion_order"] = order
            criterion["criterion"] = answer.criterion
            criterion["answer_value"] = str(answer.value)
            criterion["criterion_value"] = str(answer.value)
            criterion["reasoning"] = answer.reasoning
            criterion["evidence_ids"] = [str(identifier) for identifier in answer.evidence]
            criterion["confidence"] = answer.confidence
            normalized.append(criterion)
    return pl.DataFrame(normalized, schema=_answer_schema(query.mode))


def _answer_schema(mode: ModelMode) -> dict[str, pl.DataType | type[pl.DataType]]:
    """Return the stable answer relation schema for either contextual operation."""
    shared: dict[str, pl.DataType | type[pl.DataType]] = {
        "fact_id": pl.String,
        "answer_value": pl.String,
        "reasoning": pl.String,
        "evidence_ids": pl.List(pl.String),
        "confidence": pl.Float64,
        "provenance_backend": pl.String,
        "provenance_model": pl.String,
        "provenance_reasoning_effort": pl.String,
        "provenance_input_tokens": pl.UInt64,
        "provenance_cached_input_tokens": pl.UInt64,
        "provenance_output_tokens": pl.UInt64,
        "provenance_reasoning_tokens": pl.UInt64,
    }
    if mode is ModelMode.CLASSIFY:
        return shared
    return {
        "fact_id": pl.String,
        "criterion_order": pl.UInt64,
        "criterion": pl.String,
        "answer_value": pl.String,
        "criterion_value": pl.String,
        "reasoning": pl.String,
        "evidence_ids": pl.List(pl.String),
        "confidence": pl.Float64,
        **{name: dtype for name, dtype in shared.items() if name.startswith("provenance_")},
    }


def _provenance_columns(provenance: ModelProvenance) -> dict[str, JsonValue]:
    """Flatten model provenance into columns shared by every finding row."""
    return {
        "provenance_backend": provenance.backend,
        "provenance_model": provenance.model,
        "provenance_reasoning_effort": provenance.reasoning_effort,
        "provenance_input_tokens": provenance.input_tokens,
        "provenance_cached_input_tokens": provenance.cached_input_tokens,
        "provenance_output_tokens": provenance.output_tokens,
        "provenance_reasoning_tokens": provenance.reasoning_tokens,
    }
