from typing import Literal

import pytest

from mcmr import rule
from mcmr.engine import RuleEngine
from mcmr.facts import Fact, NodeRef, SourceSpan
from mcmr.models import Remove, SourceRewrite


class MeasurementFact(Fact):
    """Provide typed synthetic measurements to executable rule tests."""

    line_count: int
    cohesion: Literal["cohesive", "mixed"]
    is_clean: bool
    coverage: float
    label: str
    redundant_line: NodeRef | None = None


@rule
def line_count(subject: MeasurementFact) -> int:
    """Return a language-neutral source measurement.

    Definition
    ----------
    Return the provider-counted physical lines.

    Examples
    --------
    A ten-line function returns ten.

    References
    ----------
    MCMR evidence contract
    """
    return subject.line_count


line_count.function.__module__ = "mcmr.rules.general.deterministic.functions.r0099"
line_count = rule(line_count.function)


@rule
async def cohesion(subject: MeasurementFact) -> Literal["cohesive", "mixed"]:
    """Return a Python-specific provider judgment.

    Definition
    ----------
    Return one validated closed category.

    Examples
    --------
    One responsibility is cohesive.

    References
    ----------
    MCMR evidence contract
    """
    return subject.cohesion


cohesion.function.__module__ = "mcmr.rules.python.llm.architecture.r2099"
cohesion = rule(cohesion.function)


@rule
def is_clean(subject: MeasurementFact) -> bool:
    """Return a Boolean provider measurement.

    Definition
    ----------
    Return whether the measured subject is clean.

    Examples
    --------
    A clean subject returns true.

    References
    ----------
    MCMR evidence contract
    """
    return subject.is_clean


is_clean.function.__module__ = "mcmr.rules.general.deterministic.quality.r0099"
is_clean = rule(is_clean.function)


@rule
def coverage(subject: MeasurementFact) -> float:
    """Return a percentage provider measurement.

    Definition
    ----------
    Return validated measured coverage.

    Examples
    --------
    Complete coverage returns one hundred.

    References
    ----------
    MCMR evidence contract
    """
    return subject.coverage


coverage.function.__module__ = "mcmr.rules.general.deterministic.quality.r0098"
coverage = rule(coverage.function)


@rule
def label(subject: MeasurementFact) -> str:
    """Return an open text provider measurement.

    Definition
    ----------
    Return a validated text label.

    Examples
    --------
    A provider may return a stable label.

    References
    ----------
    MCMR evidence contract
    """
    return subject.label


label.function.__module__ = "mcmr.rules.general.deterministic.quality.r0097"
label = rule(label.function)


@line_count.fix(is_default=True)
def trim_lines(subject: MeasurementFact) -> list[SourceRewrite]:
    """Remove the redundant line."""
    return [Remove(target=subject.redundant_line)] if subject.redundant_line else []


def measured(*, language: str | None = None) -> MeasurementFact:
    """Build one synthetic fact with deterministic and model evidence."""
    span = SourceSpan(path="example.py", end_line=12)
    return MeasurementFact(
        key="function:example",
        span=span,
        language=language,
        line_count=12,
        cohesion="cohesive",
        is_clean=True,
        coverage=100.0,
        label="clean",
        redundant_line=NodeRef(id="line:12", span=span, kind="statement", text="pass"),
    )


@pytest.mark.anyio
async def test_rule_engine_executes_sync_and_async_rules() -> None:
    fact = measured(language="python")
    report = await RuleEngine(rules=[line_count, cohesion], fixes=[trim_lines]).run(
        {MeasurementFact: [fact]}
    )
    assert [item.value for item in report.observations] == [12, "cohesive"]
    assert report.stats.provider_read_count == 1
    assert report.stats.fix_candidate_count == 1


@pytest.mark.anyio
async def test_general_rule_accepts_another_language() -> None:
    report = await RuleEngine(rules=[line_count]).run(
        {MeasurementFact: [measured(language="rust")]}
    )
    assert report.observations[0].value == 12


@pytest.mark.anyio
async def test_python_rule_skips_another_language() -> None:
    """A rule scoped to one language reads nothing from another and is reported as skipped."""
    report = await RuleEngine(rules=[cohesion]).run(
        {MeasurementFact: [measured(language="typescript")]}
    )

    assert report.observations == []
    assert report.stats.skipped_rule_count == 1


def test_fix_plan_rewrites_the_addressed_node() -> None:
    plan = trim_lines(measured())
    assert plan is not None
    assert plan.summary == "Remove the redundant line."
    assert [span.start_line for span in plan.spans] == [1]


def test_fix_plan_returns_none_without_an_addressed_node() -> None:
    assert trim_lines(measured().model_copy(update={"redundant_line": None})) is None


@pytest.mark.anyio
async def test_rule_engine_validates_each_scalar_output() -> None:
    report = await RuleEngine(rules=[is_clean, coverage, label]).run(
        {MeasurementFact: [measured()]}
    )
    assert [item.value for item in report.observations] == [True, 100.0, "clean"]


@pytest.mark.anyio
async def test_rule_engine_requires_each_provider_stream() -> None:
    with pytest.raises(KeyError, match="MeasurementFact"):
        await RuleEngine(rules=[line_count]).run({})


@pytest.mark.anyio
async def test_rule_engine_rejects_an_unsupported_runtime_value() -> None:
    invalid = MeasurementFact.model_construct(
        key="invalid",
        span=SourceSpan(path="invalid.py"),
        label=[],
    )
    with pytest.raises(TypeError, match="unsupported value"):
        await RuleEngine(rules=[label]).run({MeasurementFact: [invalid]})


@pytest.mark.anyio
async def test_rule_engine_rejects_a_wrong_scalar_type() -> None:
    invalid = MeasurementFact.model_construct(
        key="invalid",
        span=SourceSpan(path="invalid.py"),
        is_clean=1,
    )
    with pytest.raises(TypeError, match="invalid bool value"):
        await RuleEngine(rules=[is_clean]).run({MeasurementFact: [invalid]})
