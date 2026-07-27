from typing import Literal

import pytest

from mcmr import rule
from mcmr.engine import MockBackend, MockEngine
from mcmr.facts import ImportBindingFact, SourceSpan
from mcmr.models import Occurrence, SourceRewrite


def bindings() -> list[ImportBindingFact]:
    """Build deterministic facts for mock execution tests."""
    return [
        ImportBindingFact(
            key=f"module:{name}",
            span=SourceSpan(path="example.py", start_line=line, end_line=line),
            name=name,
            module=name,
        )
        for line, name in enumerate(("json", "pathlib"), start=1)
    ]


@pytest.mark.anyio
async def test_mock_engine_plans_each_fact_stream_once() -> None:
    @rule
    def unused_import(subject: ImportBindingFact) -> Occurrence:
        return not subject.has_qualifying_use

    @rule
    async def import_intent(
        subject: ImportBindingFact,
    ) -> Literal["used", "unused"]:
        return "used" if subject.has_qualifying_use else "unused"

    @unused_import.fix(is_default=True)
    def remove_unused_import(subject: ImportBindingFact) -> list[SourceRewrite]:
        return []

    engine = MockEngine(rules=[unused_import, import_intent], fixes=[remove_unused_import])
    report = await engine.run({ImportBindingFact: bindings()})
    assert report.stats.rule_count == 2
    assert report.stats.fact_count == 2
    assert report.stats.invocation_count == 4
    assert report.stats.provider_read_count == 1
    assert report.stats.fix_count == 1
    assert report.stats.fix_candidate_count == 2
    assert len(report.observations) == 4
    assert report.stats.total_nanoseconds >= report.stats.execution_nanoseconds


@pytest.mark.anyio
async def test_mock_engine_requires_the_exact_fact_type() -> None:
    @rule
    def unused_import(subject: ImportBindingFact) -> Occurrence:
        return not subject.has_qualifying_use

    with pytest.raises(KeyError, match="ImportBindingFact"):
        await MockEngine(rules=[unused_import]).run({})


@pytest.mark.anyio
async def test_mock_backend_returns_an_empty_string_for_text_outputs() -> None:
    @rule
    def rendered_name(subject: ImportBindingFact) -> str:
        return subject.name

    assert await MockBackend().evaluate(rendered_name, bindings()[0]) == ""
