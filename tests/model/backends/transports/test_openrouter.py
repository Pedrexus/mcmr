from typing import TYPE_CHECKING

import pytest
from httpx import ConnectError

from mcmr.execution import CriterionValue, OpenRouterBackend
from mcmr.execution.backends import CandidateProtocol
from mcmr.facts import Evidence

from ...backend_values import assessment_payload, candidate, cited, criteria, payload
from ...fakes import Category, RouterProbe

if TYPE_CHECKING:
    from pydantic import JsonValue


@pytest.fixture(autouse=True)
def api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give every request a controlled key that never leaves the environment."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")


@pytest.mark.anyio
async def test_a_valid_completion_becomes_one_cited_and_accounted_classification() -> None:
    """One live-shaped completion becomes one auditable classification."""
    probe = RouterProbe(RouterProbe.completion(payload()))
    backend = OpenRouterBackend(transport=probe.transport, model="vendor/model")

    answer = await backend.classify_candidate(
        cited(), category=Category, instructions="Judge only the retained structure."
    )

    assert (answer.value, answer.evidence, answer.confidence) == (
        Category.SUPPORTED,
        ["structure"],
        0.75,
    )
    assert (answer.provenance.backend, answer.provenance.model) == (
        "openrouter",
        "vendor/model-served",
    )
    assert (
        answer.provenance.input_tokens,
        answer.provenance.cached_input_tokens,
        answer.provenance.output_tokens,
        answer.provenance.reasoning_tokens,
    ) == (12, 3, 4, 2)


@pytest.mark.anyio
async def test_one_authorized_request_carries_the_closed_schema() -> None:
    """The client spends one bounded request on a schema-constrained prompt."""
    probe = RouterProbe(RouterProbe.completion(payload()))
    backend = OpenRouterBackend(
        transport=probe.transport,
        model="vendor/model",
        reasoning_effort="high",
    )

    await backend.classify_candidate(
        cited(), category=Category, instructions="Judge only the retained structure."
    )

    schema = CandidateProtocol(
        candidate=cited(),
        instructions="Judge only the retained structure.",
    ).classification_schema(Category)
    sent = probe.sent()
    assert (sent["model"], sent["reasoning"]) == ("vendor/model", {"effort": "high"})
    assert sent["response_format"] == {
        "type": "json_schema",
        "json_schema": {"name": "classification", "strict": True, "schema": schema},
    }
    assert (probe.authorization(), str(probe.requests[0].url)) == (
        "Bearer test-key",
        "https://openrouter.ai/api/v1/chat/completions",
    )


@pytest.mark.anyio
async def test_batches_reach_the_server_once_and_split_their_reported_usage() -> None:
    """Both model modes answer a bounded batch in one request and account for its tokens once."""
    cases = [
        candidate(Evidence(signal="first", detail="one", source="first.py")),
        candidate(Evidence(signal="second", detail="two", source="second.py")),
    ]
    classified = RouterProbe(
        RouterProbe.batched([payload(evidence=("first",)), payload(evidence=("second",))])
    )
    assessed = RouterProbe(
        RouterProbe.batched(
            [assessment_payload(evidence="first"), assessment_payload(evidence="second")]
        )
    )

    answers = await OpenRouterBackend(transport=classified.transport, batch_size=2).classify_many(
        cases, category=Category, instructions="Judge each structure."
    )
    predicates = await OpenRouterBackend(transport=assessed.transport, batch_size=2).assess_many(
        cases, criteria=criteria(), instructions="Assess each structure."
    )

    assert ([answer.evidence for answer in answers], len(classified.requests)) == (
        [["first"], ["second"]],
        1,
    )
    assert [answer.value("structure supported") for answer in predicates] == [
        CriterionValue.YES,
        CriterionValue.YES,
    ]
    assert sum(answer.provenance.input_tokens for answer in answers) == 12
    assert "reasoning" not in classified.sent()


@pytest.mark.anyio
async def test_an_empty_relation_never_reaches_the_server() -> None:
    """An empty contextual relation remains an empty result in both model modes."""
    probe = RouterProbe(RouterProbe.completion(payload()))
    backend = OpenRouterBackend(transport=probe.transport)

    assert await backend.classify_many([], category=Category, instructions="Judge.") == []
    assert await backend.assess_many([], criteria=criteria(), instructions="Assess.") == []
    assert probe.requests == []


@pytest.mark.anyio
async def test_a_missing_key_refuses_the_request_before_it_is_sent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A backend without credentials explains itself instead of calling an anonymous server."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    probe = RouterProbe(RouterProbe.completion(payload()))
    backend = OpenRouterBackend(transport=probe.transport)

    with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
        await backend.classify_candidate(
            candidate(), category=Category, instructions="Judge the structure."
        )
    isolated = await backend.classify_many(
        [candidate()], category=Category, instructions="Judge the structure."
    )

    assert probe.requests == []
    assert (isolated[0].value, "OPENROUTER_API_KEY" in isolated[0].reasoning) == (
        Category.UNCERTAIN,
        True,
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("probe", "message"),
    [
        (RouterProbe({"error": {"message": "no credits"}}, status_code=402), "402"),
        (RouterProbe("<html>gateway</html>", status_code=503), "gateway"),
        (RouterProbe("not json at all"), "could not answer"),
        (RouterProbe({"choices": []}), "no answer"),
        (RouterProbe({"choices": [{"message": {"content": "  "}}]}), "no answer"),
        (
            RouterProbe(RouterProbe.completion(payload()), failure=ConnectError("refused")),
            "could not answer",
        ),
    ],
)
async def test_every_unusable_response_raises_one_bounded_diagnostic(
    probe: RouterProbe,
    message: str,
) -> None:
    """A transport, status, or shape failure never masquerades as a classification."""
    with pytest.raises(RuntimeError, match=message):
        await OpenRouterBackend(transport=probe.transport).classify_candidate(
            candidate(), category=Category, instructions="Judge the structure."
        )


@pytest.mark.anyio
@pytest.mark.parametrize(
    "usage",
    [None, {}, {"prompt_tokens": -3, "completion_tokens": "4"}],
    ids=["absent", "empty", "invalid"],
)
async def test_absent_or_invalid_telemetry_never_invents_counts(usage: JsonValue) -> None:
    """An unreported usage record stays honest and keeps the configured model name."""
    body = RouterProbe.completion(payload(), model="   ", usage=usage)
    if usage is None:
        del body["usage"]
    probe = RouterProbe(body)

    answer = await OpenRouterBackend(
        transport=probe.transport, model="configured/model"
    ).classify_candidate(cited(), category=Category, instructions="Judge the structure.")

    assert answer.provenance.model == "configured/model"
    assert (
        answer.provenance.input_tokens,
        answer.provenance.cached_input_tokens,
        answer.provenance.output_tokens,
        answer.provenance.reasoning_tokens,
    ) == (0, 0, 0, 0)
