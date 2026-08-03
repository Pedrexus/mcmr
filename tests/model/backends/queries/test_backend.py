import json
from typing import TYPE_CHECKING

import pytest
from pydantic import ValidationError

from mcmr.domain.contracts import Criterion
from mcmr.execution import Classification, CodexBackend, CommandResult, CriterionValue
from mcmr.execution.backends import CodexHarness, CodexProtocol
from mcmr.facts import Evidence

from ...backend_fakes import Category, StubRunner
from ...backend_values import (
    assessment_payload,
    candidate,
    completed,
    criteria,
    payload,
    provenance,
)

if TYPE_CHECKING:
    from collections.abc import Sequence


@pytest.mark.anyio
async def test_a_valid_answer_retains_reasoning_citations_usage_and_provenance() -> None:
    """One live-shaped response becomes one auditable classification and finding."""
    runner = StubRunner(payload(), CommandResult(returncode=0, stdout=completed()))
    claim = Evidence(signal="structure", detail="two modules", source="kernel:structure")
    stated = candidate(claim)
    answer = await CodexBackend(runner=runner, timeout_seconds=17).classify_candidate(
        stated,
        category=Category,
        instructions="Judge only the retained structure.",
    )

    assert (
        answer.value,
        answer.evidence,
        answer.confidence,
        answer.provenance.model,
        answer.provenance.input_tokens,
        answer.provenance.cached_input_tokens,
        answer.provenance.output_tokens,
        answer.provenance.reasoning_tokens,
    ) == (Category.SUPPORTED, ["structure"], 0.75, "gpt-tested", 12, 3, 4, 2)
    assert runner.schema == CodexProtocol(
        candidate=stated,
        instructions="Judge only the retained structure.",
    ).classification_schema(Category)
    assert runner.calls[0][3] == 17


@pytest.mark.anyio
async def test_one_codex_turn_assesses_every_criterion_before_local_reduction() -> None:
    runner = StubRunner(assessment_payload(), CommandResult(returncode=0, stdout=completed()))
    stated = candidate(
        Evidence(signal="structure", detail="two modules", source="kernel:structure")
    )
    answer = await CodexBackend(runner=runner).assess_candidate(
        stated,
        criteria=criteria(),
        instructions="Assess the retained structure without selecting policy.",
    )

    assert answer.value("structure supported") is CriterionValue.YES
    assert answer.value("structure contradicted") is CriterionValue.NO
    assert len(runner.calls) == 1
    assert runner.schema == CodexProtocol(
        candidate=stated,
        instructions="Assess the retained structure without selecting policy.",
    ).assessment_schema(criteria())
    assert "You never select the rule's final category" in runner.calls[0][1]
    assert "not the probability that the predicate is true" in runner.calls[0][1]


@pytest.mark.anyio
async def test_assessment_contract_rejects_empty_duplicate_changed_and_uncited_criteria() -> None:
    async def rejected(
        runner: StubRunner,
        stated_criteria: Sequence[Criterion],
        message: str,
    ) -> None:
        """Require one controlled assessment contract failure."""
        with pytest.raises(ValueError, match=message):
            await CodexBackend(runner=runner).assess_candidate(
                candidate(), criteria=stated_criteria, instructions="Assess facts."
            )

    valid = StubRunner(assessment_payload(), CommandResult(returncode=0))
    await rejected(valid, [], "at least one criterion")
    await rejected(valid, [criteria()[0], criteria()[0]], "must be unique")
    await rejected(
        StubRunner(
            {
                "criteria": {
                    "different": {
                        "value": "yes",
                        "reasoning": "Different criterion.",
                        "evidence_ids": ["fact:design:shop/service.py"],
                        "confidence": 0.5,
                    }
                }
            },
            CommandResult(returncode=0),
        ),
        criteria(),
        "different assessment criteria",
    )
    await rejected(
        StubRunner(assessment_payload(evidence="invented"), CommandResult(returncode=0)),
        criteria(),
        "unknown evidence",
    )


@pytest.mark.anyio
async def test_missing_usage_and_model_fall_back_without_inventing_counts() -> None:
    """An older event stream remains usable while honestly reporting absent telemetry."""
    runner = StubRunner(payload(), CommandResult(returncode=0, stdout='{"type":"item"}'))
    answer = await CodexBackend(runner=runner, model="configured").classify_candidate(
        candidate(Evidence(signal="structure", detail="two modules", source="kernel:structure")),
        category=Category,
        instructions="Judge the structure.",
    )

    assert answer.provenance.model == "configured"
    assert answer.provenance.input_tokens == 0
    assert answer.provenance.cached_input_tokens == 0
    assert answer.provenance.output_tokens == 0
    assert answer.provenance.reasoning_tokens == 0


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("stdout", "stderr", "diagnostic"),
    [
        ("standard output", "", "standard output"),
        ("ignored output", "standard error", "standard error"),
    ],
)
async def test_a_failed_harness_reports_the_best_bounded_diagnostic(
    *, stdout: str, stderr: str, diagnostic: str
) -> None:
    """A process failure never masquerades as a classification or loses its explanation."""
    runner = StubRunner(None, CommandResult(returncode=7, stdout=stdout, stderr=stderr))
    with pytest.raises(RuntimeError, match=diagnostic):
        await CodexBackend(runner=runner).classify_candidate(
            candidate(), category=Category, instructions="Judge the structure."
        )


@pytest.mark.anyio
async def test_unknown_repeated_and_empty_citations_are_rejected() -> None:
    """Every cited identifier must name one distinct retained claim."""

    async def rejected(
        runner: StubRunner,
        message: str,
        error: type[ValueError],
        instructions: str = "Judge the structure.",
    ) -> None:
        with pytest.raises(error, match=message):
            await CodexBackend(runner=runner).classify_candidate(
                candidate(claim), category=Category, instructions=instructions
            )

    claim = Evidence(signal="structure", detail="two modules", source="kernel:structure")
    await rejected(
        StubRunner(payload(evidence=("invented",)), CommandResult(returncode=0)),
        "unknown evidence",
        ValueError,
    )
    await rejected(
        StubRunner(payload(evidence=("structure", "structure")), CommandResult(returncode=0)),
        "evidence_ids",
        ValidationError,
    )
    empty = StubRunner(payload(), CommandResult(returncode=0))
    await rejected(empty, "at least 1 character", ValidationError, "   ")
    assert not empty.calls


def test_usage_ignores_invalid_counts_and_blank_reported_models() -> None:
    """Malformed optional telemetry cannot enter a nonnegative provenance record."""
    event = json.dumps(
        {
            "type": "turn.completed",
            "model": "   ",
            "usage": {
                "input_tokens": True,
                "cached_input_tokens": -1,
                "output_tokens": "4",
                "reasoning_output_tokens": 2,
            },
        }
    )
    assert CodexHarness().usage(event) == (0, 0, 0, 2, "")
    assert CodexHarness().usage('{"type":"turn.completed","usage":[]}') == (0, 0, 0, 0, "")


def test_nonempty_evidence_identifiers_reject_whitespace() -> None:
    """Illegal citation identifiers are rejected at the transport boundary."""
    with pytest.raises(ValidationError, match="at least 1 character"):
        Evidence(signal="   ", detail="detail", source="kernel")


def test_the_controlled_backend_cites_at_most_the_schema_limit() -> None:
    """Local contract fixtures produce the same bounded citation shape as Codex."""
    claims = [
        Evidence(signal=f"claim-{index}", detail="detail", source="kernel") for index in range(10)
    ]
    answer = Classification(
        value=Category.SUPPORTED,
        reasoning="Controlled classification for contract verification.",
        evidence=list(candidate(*claims).retained)[:8],
        confidence=1.0,
        provenance=provenance(),
    )
    assert answer.evidence == [f"claim-{index}" for index in range(8)]
