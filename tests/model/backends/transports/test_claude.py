import json

import pytest
from pydantic import JsonValue, TypeAdapter

from mcmr.execution import ClaudeBackend, CommandResult, CriterionValue
from mcmr.execution.backends import CandidateProtocol
from mcmr.facts import Evidence

from ...backend_values import (
    assessment_payload,
    candidate,
    cited,
    criteria,
    payload,
    printed_turn,
)
from ...fakes import Category, StubRunner


@pytest.mark.anyio
async def test_a_printed_turn_becomes_one_cited_and_accounted_classification() -> None:
    """One live-shaped printed turn becomes one auditable classification."""
    runner = StubRunner(None, printed_turn(payload()))
    backend = ClaudeBackend(runner=runner, model="claude-sonnet-5", reasoning_effort="high")

    answer = await backend.classify_candidate(
        cited(), category=Category, instructions="Judge only the retained structure."
    )

    assert (answer.value, answer.evidence, answer.confidence) == (
        Category.SUPPORTED,
        ["structure"],
        0.75,
    )
    assert (answer.provenance.backend, answer.provenance.model) == (
        "claude",
        "claude-sonnet-5-20260210",
    )
    assert (
        answer.provenance.input_tokens,
        answer.provenance.cached_input_tokens,
        answer.provenance.output_tokens,
        answer.provenance.reasoning_tokens,
    ) == (12, 3, 4, 0)


@pytest.mark.anyio
async def test_one_stateless_command_carries_the_closed_schema() -> None:
    """The harness spends one isolated process on a schema-constrained prompt."""
    runner = StubRunner(None, printed_turn(payload()))
    backend = ClaudeBackend(
        runner=runner,
        model="claude-sonnet-5",
        reasoning_effort="high",
        timeout_seconds=17,
    )

    await backend.classify_candidate(
        cited(), category=Category, instructions="Judge only the retained structure."
    )

    command, prompt, _, timeout_seconds = runner.calls[0]
    schema = CandidateProtocol(
        candidate=cited(),
        instructions="Judge only the retained structure.",
    ).classification_schema(Category)
    assert TypeAdapter(dict[str, JsonValue]).validate_json(runner.flag("--json-schema")) == schema
    assert (
        command[:2],
        runner.flag("--model"),
        runner.flag("--output-format"),
        runner.flag("--effort"),
        runner.flag("--tools"),
    ) == (["claude", "--print"], "claude-sonnet-5", "json", "high", "")
    assert {"--safe-mode", "--strict-mcp-config", "--no-session-persistence"} <= set(command)
    assert ("Judge only the retained structure" in prompt, timeout_seconds) == (True, 17)


@pytest.mark.anyio
async def test_a_silent_reasoning_effort_never_reaches_the_command() -> None:
    """A backend asked for no reasoning runs the model at its own default effort."""
    runner = StubRunner(None, printed_turn(payload()))

    await ClaudeBackend(runner=runner).classify_candidate(
        cited(), category=Category, instructions="Judge the structure."
    )

    assert "--effort" not in runner.calls[0][0]


@pytest.mark.anyio
async def test_batches_run_one_process_and_split_their_reported_usage() -> None:
    """Both model modes answer a bounded batch in one process and account for its tokens once."""
    cases = [
        candidate(Evidence(signal="first", detail="one", source="first.py")),
        candidate(Evidence(signal="second", detail="two", source="second.py")),
    ]
    keyed: JsonValue = {"0": payload(evidence=("first",)), "1": payload(evidence=("second",))}
    predicates: JsonValue = {
        "0": assessment_payload(evidence="first"),
        "1": assessment_payload(evidence="second"),
    }
    classified = StubRunner(None, printed_turn({"answers": keyed}))
    assessed = StubRunner(None, printed_turn({"answers": predicates}))

    answers = await ClaudeBackend(runner=classified, batch_size=2).classify_many(
        cases, category=Category, instructions="Judge each structure."
    )
    reviewed = await ClaudeBackend(runner=assessed, batch_size=2).assess_many(
        cases, criteria=criteria(), instructions="Assess each structure."
    )

    assert ([answer.evidence for answer in answers], len(classified.calls)) == (
        [["first"], ["second"]],
        1,
    )
    assert [answer.value("structure supported") for answer in reviewed] == [
        CriterionValue.YES,
        CriterionValue.YES,
    ]
    assert sum(answer.provenance.input_tokens for answer in answers) == 12


@pytest.mark.anyio
async def test_a_turn_without_structured_output_falls_back_to_its_printed_result() -> None:
    """An older result object stays usable through the text answer it printed."""
    runner = StubRunner(None, printed_turn(payload(), structured=False))

    answer = await ClaudeBackend(runner=runner).classify_candidate(
        cited(), category=Category, instructions="Judge the structure."
    )

    assert answer.value is Category.SUPPORTED


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("result", "message"),
    [
        (CommandResult(returncode=7, stdout="ignored", stderr="not logged in"), "not logged in"),
        (CommandResult(returncode=7, stdout="broken run"), "broken run"),
        (
            CommandResult(returncode=0, stdout=json.dumps({"is_error": True, "result": "denied"})),
            "failed turn",
        ),
        (
            CommandResult(returncode=0, stdout=json.dumps({"is_error": False, "result": "  "})),
            "no structured answer",
        ),
    ],
)
async def test_every_unusable_turn_raises_one_bounded_diagnostic(
    result: CommandResult,
    message: str,
) -> None:
    """A process failure never masquerades as a classification or loses its explanation."""
    with pytest.raises(RuntimeError, match=message):
        await ClaudeBackend(runner=StubRunner(None, result)).classify_candidate(
            candidate(), category=Category, instructions="Judge the structure."
        )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "usage",
    [None, {}, {"input_tokens": True, "output_tokens": "4"}],
    ids=["absent", "empty", "invalid"],
)
async def test_absent_or_invalid_telemetry_never_invents_counts(usage: JsonValue) -> None:
    """An unreported usage record stays honest and keeps the configured model name."""
    printed = printed_turn(payload(), model="   ", usage=usage)
    turn = TypeAdapter(dict[str, JsonValue]).validate_json(printed.stdout)
    if usage is None:
        del turn["usage"]
    runner = StubRunner(None, CommandResult(returncode=0, stdout=json.dumps(turn)))

    answer = await ClaudeBackend(runner=runner, model="configured-model").classify_candidate(
        cited(), category=Category, instructions="Judge the structure."
    )

    assert answer.provenance.model == "configured-model"
    assert (
        answer.provenance.input_tokens,
        answer.provenance.cached_input_tokens,
        answer.provenance.output_tokens,
        answer.provenance.reasoning_tokens,
    ) == (0, 0, 0, 0)


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("billed", "model", "counts"),
    [
        (
            {
                "claude-haiku-4-5-20251001": {"inputTokens": 4230, "outputTokens": 196},
                "claude-sonnet-5-20260210": {
                    "inputTokens": 538,
                    "cacheReadInputTokens": 7,
                    "outputTokens": 211,
                },
            },
            "claude-sonnet-5-20260210",
            (538, 7, 211),
        ),
        ({}, "configured-model", (99, 98, 97)),
        (
            {
                "claude-haiku-4-5-20251001": {"outputTokens": 5},
                "claude-sonnet-5-20260210": {"outputTokens": 5},
            },
            "configured-model",
            (99, 98, 97),
        ),
    ],
    ids=["side-model-billed-first", "nothing-billed", "tied"],
)
async def test_provenance_follows_the_model_that_answered(
    billed: JsonValue,
    model: str,
    counts: tuple[int, int, int],
) -> None:
    """A session that bills a safety classifier beside the answering model still reports it."""
    runner = StubRunner(None, printed_turn(payload(), billed=billed))

    answer = await ClaudeBackend(runner=runner, model="configured-model").classify_candidate(
        cited(), category=Category, instructions="Judge the structure."
    )

    assert answer.provenance.model == model
    assert (
        answer.provenance.input_tokens,
        answer.provenance.cached_input_tokens,
        answer.provenance.output_tokens,
    ) == counts
