import asyncio
import json
from typing import TYPE_CHECKING

import pytest
from pydantic import JsonValue, ValidationError

from mcmr.domain.contracts import Criterion
from mcmr.execution import Classification, CodexBackend, CommandResult, CriterionValue
from mcmr.execution.backends import CandidateProtocol, CodexHarness
from mcmr.facts import Evidence

from ...backend_values import (
    assessment_payload,
    candidate,
    completed,
    criteria,
    payload,
    provenance,
)
from ...fakes import Category, StubRunner

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
    assert runner.schema == CandidateProtocol(
        candidate=stated,
        instructions="Judge only the retained structure.",
    ).classification_schema(Category)
    assert runner.calls[0][3] == 17


@pytest.mark.anyio
async def test_codex_batches_candidates_and_preserves_exact_aggregate_usage() -> None:
    """Both model modes use one process for a bounded batch and account for its tokens once."""
    first = candidate(Evidence(signal="first", detail="one", source="first.py"))
    second = candidate(Evidence(signal="second", detail="two", source="second.py"))
    cases = [first, second]
    runner = StubRunner(
        {
            "answers": {
                "0": payload(evidence=("first",)),
                "1": payload(evidence=("second",)),
            }
        },
        CommandResult(returncode=0, stdout=completed()),
    )
    answers = await CodexBackend(runner=runner, batch_size=2).classify_many(
        cases, category=Category, instructions="Judge each structure."
    )
    assessment_runner = StubRunner(
        {
            "answers": {
                "0": assessment_payload(evidence="first"),
                "1": assessment_payload(evidence="second"),
            }
        },
        CommandResult(returncode=0, stdout=completed()),
    )
    assessed = await CodexBackend(runner=assessment_runner, batch_size=2).assess_many(
        cases, criteria=criteria(), instructions="Assess each structure."
    )

    assert ([answer.evidence for answer in answers], len(runner.calls)) == (
        [["first"], ["second"]],
        1,
    )
    assert [answer.value("structure supported") for answer in assessed] == [
        CriterionValue.YES,
        CriterionValue.YES,
    ]
    assert sum(answer.provenance.input_tokens for answer in answers) == 12


@pytest.mark.anyio
async def test_a_batch_answer_reaches_the_candidate_its_key_names() -> None:
    """Keys bind answers to candidates, and an answer on the wrong one cannot pass as evidence."""
    cases = [
        candidate(Evidence(signal=f"signal{index}", detail="one", source="one.py"))
        for index in range(12)
    ]
    keyed: dict[str, JsonValue] = {
        str(index): payload(evidence=(f"signal{index}",)) for index in range(12)
    }
    # A batch object arrives in whatever order the model wrote it, which for numeric keys is
    # never the numeric order, so an answer that travelled by position would land elsewhere.
    scrambled = {key: keyed[key] for key in sorted(keyed, reverse=True)}
    answers = await CodexBackend(
        runner=StubRunner(
            {"answers": scrambled},
            CommandResult(returncode=0, stdout=completed()),
        ),
        batch_size=12,
    ).classify_many(cases, category=Category, instructions="Judge each structure.")
    swapped = await CodexBackend(
        runner=StubRunner(
            {"answers": {"0": keyed["1"], "1": keyed["0"]}},
            CommandResult(returncode=0, stdout=completed()),
        ),
        batch_size=2,
    ).classify_many(cases[:2], category=Category, instructions="Judge each structure.")

    assert [answer.evidence for answer in answers] == [[f"signal{index}"] for index in range(12)]
    assert [answer.value for answer in swapped] == [Category.UNCERTAIN, Category.UNCERTAIN]
    assert "cited unknown evidence" in swapped[0].reasoning


@pytest.mark.anyio
async def test_codex_empty_batches_start_no_process() -> None:
    """An empty contextual relation remains an empty result in both model modes."""
    runner = StubRunner({}, CommandResult(returncode=0))
    backend = CodexBackend(runner=runner)

    classified = await backend.classify_many(
        [], category=Category, instructions="Judge each structure."
    )
    assessed = await backend.assess_many(
        [], criteria=criteria(), instructions="Assess each structure."
    )

    assert classified == []
    assert assessed == []
    assert runner.calls == []


@pytest.mark.anyio
async def test_codex_malformed_batch_keys_fail_only_their_batch() -> None:
    """A response that changes candidate identities becomes local uncertainty."""
    stated = candidate()
    malformed: dict[str, JsonValue] = {"answers": {"unexpected": payload()}}
    classified = await CodexBackend(
        runner=StubRunner(malformed, CommandResult(returncode=0))
    ).classify_many([stated], category=Category, instructions="Judge each structure.")
    assessed = await CodexBackend(
        runner=StubRunner(malformed, CommandResult(returncode=0))
    ).assess_many([stated], criteria=criteria(), instructions="Assess each structure.")

    assert classified[0].value is Category.UNCERTAIN
    assert "different batch candidate keys" in classified[0].reasoning
    assert all(answer.value is CriterionValue.UNKNOWN for answer in assessed[0].answers)


@pytest.mark.anyio
async def test_codex_shares_one_worker_bound_across_concurrent_rules() -> None:
    """Parallel rule queries cannot multiply the configured process pool."""
    first = candidate(Evidence(signal="first", detail="one", source="first.py"))
    second = candidate(Evidence(signal="second", detail="two", source="second.py"))
    runner = StubRunner(
        {
            "answers": {
                "0": payload(evidence=("first",)),
                "1": payload(evidence=("second",)),
            }
        },
        CommandResult(returncode=0, stdout=completed()),
        delay_seconds=0.01,
    )
    backend = CodexBackend(runner=runner, workers=1, batch_size=2)

    await asyncio.gather(
        backend.classify_many(
            [first, second], category=Category, instructions="Judge each structure."
        ),
        backend.classify_many(
            [first, second], category=Category, instructions="Judge each structure."
        ),
    )

    assert (len(runner.calls), runner.maximum_active) == (2, 1)


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
    assert runner.schema == CandidateProtocol(
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
