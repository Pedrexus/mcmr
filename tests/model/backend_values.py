import json

from pydantic import JsonValue, TypeAdapter

from mcmr.contextual.corpus import (
    ContextualCase,
    ContextualExpectation,
)
from mcmr.domain.contracts import (
    Criterion,
    ModelProvenance,
)
from mcmr.execution import (
    ModelCandidate,
)
from mcmr.facts import Evidence


def provenance() -> ModelProvenance:
    """Build stable provenance for controlled batch backends."""
    return ModelProvenance(
        backend="controlled",
        model="test",
        reasoning_effort="none",
    )


def criteria() -> tuple[Criterion, Criterion]:
    """Build the independent predicates used by controlled assessment turns."""
    return (
        Criterion(name="structure supported", question="Does retained evidence support it?"),
        Criterion(name="structure contradicted", question="Does retained evidence contradict it?"),
    )


def candidate(*claims: Evidence) -> ModelCandidate:
    """Build one normalized model candidate with selected retained claims."""
    return ModelCandidate(
        fact_id="design:shop/service.py",
        path="shop/service.py",
        subject={"fields": {"kind": "design"}, "records": [], "values": []},
        evidence=claims
        or (
            Evidence(
                signal="fact:design:shop/service.py",
                detail='{"kind":"design"}',
                source="shop/service.py",
            ),
        ),
    )


def payload(*, evidence: tuple[str, ...] = ("structure",)) -> dict[str, JsonValue]:
    """Return one valid schema-constrained model answer."""
    return TypeAdapter(dict[str, JsonValue]).validate_python(
        {
            "category": "supported",
            "reasoning": "The retained structure supports this classification.",
            "evidence_ids": list(evidence),
            "confidence": 0.75,
        }
    )


def assessment_payload(*, evidence: str = "structure") -> dict[str, JsonValue]:
    """Return one valid independent-criteria answer."""
    answer = {
        "value": "yes",
        "reasoning": "The retained structure establishes this predicate.",
        "evidence_ids": [evidence],
        "confidence": 0.8,
    }
    return TypeAdapter(dict[str, JsonValue]).validate_python(
        {
            "criteria": {
                "structure supported": answer,
                "structure contradicted": {**answer, "value": "no"},
            }
        }
    )


def completed(model: str = "gpt-tested") -> str:
    """Return the final JSON event emitted by one controlled Codex turn."""
    return json.dumps(
        {
            "type": "turn.completed",
            "model": model,
            "usage": {
                "input_tokens": 12,
                "cached_input_tokens": 3,
                "output_tokens": 4,
                "reasoning_output_tokens": 2,
            },
        }
    )


def contextual_case(
    rule: str,
    expected: ContextualExpectation,
    name: str = "representative",
) -> ContextualCase:
    """Build one reviewed contextual case for experiment contract tests."""
    return ContextualCase(
        name=name,
        rule=rule,
        fact_id=f"case:{rule}",
        path="src/example.py",
        subject={"structure": "reviewed"},
        evidence=[Evidence(signal="reviewed", detail="human label", source="review")],
        expected=expected,
    )
