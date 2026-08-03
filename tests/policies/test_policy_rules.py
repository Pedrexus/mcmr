import pytest
from pydantic import ValidationError

from mcmr import validated_setting
from mcmr.domain.contracts import RuleContract, RuleSetting, RuleValue
from mcmr.facts import (
    AlertDefinition,
    AlertFact,
    AutomationTask,
    AutomationTaskFact,
    ChangeApproval,
    ChangeFact,
    ChangeRecord,
    CICheck,
    CICheckFact,
    CIConfigurationFact,
    CIWorkflow,
    CommentFact,
    CommentGroup,
    Fact,
    NodeRef,
    PerformanceBudget,
    PerformanceDecisionFact,
    RunbookFact,
    RunbookTrigger,
    ServiceObjective,
    ServiceObjectiveFact,
    SourceSpan,
)
from mcmr.rules.general import (
    alert_actionability,
    comment_length,
    continuous_integration,
    feedback_target_coverage,
    onboarding_readiness,
    project_automation,
    regression_guard_coverage,
    review_coverage,
    runbook_coverage,
    service_objective_coverage,
)

from ..support import query_value, retained_query

_SPAN = SourceSpan(path="project")


def value(subject: Fact, rule: RuleContract, **settings: RuleSetting) -> RuleValue:
    """Return one scalar from a rule invoked once over its retained table."""
    return query_value(retained_query(subject, rule, **settings))


def comment(*groups: CommentGroup) -> CommentFact:
    """Return one comment fact holding the given contiguous groups."""
    return CommentFact(key="comment", span=_SPAN, groups=list(groups))


def test_continuous_integration_cases() -> None:
    absent = CIConfigurationFact(key="ci", span=_SPAN)
    partial = absent.model_copy(
        update={"workflows": [CIWorkflow(name="checks", tasks=["test"], is_change_blocking=True)]}
    )
    complete = partial.model_copy(
        update={
            "workflows": [
                CIWorkflow(
                    name="checks",
                    tasks=["lint", "typecheck", "test"],
                    triggers=["pull_request"],
                    is_change_blocking=True,
                )
            ]
        }
    )
    fragile = complete.model_copy(
        update={
            "workflows": [
                complete.workflows[0].model_copy(update={"uses_locked_dependencies": False})
            ]
        }
    )
    manual = complete.model_copy(
        update={
            "workflows": [complete.workflows[0].model_copy(update={"is_change_blocking": False})]
        }
    )

    assert value(absent, continuous_integration) == "absent"
    assert value(partial, continuous_integration) == "partial"
    assert value(complete, continuous_integration) == "complete"
    assert value(fragile, continuous_integration) == "fragile"
    assert value(manual, continuous_integration) == "absent"


def test_feedback_target_coverage_cases() -> None:
    no_required_checks = CICheckFact(key="ci-checks", span=_SPAN)
    checks = no_required_checks.model_copy(
        update={
            "checks": [
                CICheck(name="lint", duration_percentile_seconds=30),
                CICheck(name="test", duration_percentile_seconds=700),
                CICheck(
                    name="nightly",
                    duration_percentile_seconds=3600,
                    is_change_blocking=False,
                ),
            ]
        }
    )
    lower_confidence = checks.model_copy(
        update={"checks": [CICheck(name="lint", duration_percentile_seconds=30, percentile=0.5)]}
    )

    assert value(no_required_checks, feedback_target_coverage) == 0.0
    assert value(checks, feedback_target_coverage) == 50.0
    assert value(checks, feedback_target_coverage, target_seconds=700) == 100.0
    assert value(lower_confidence, feedback_target_coverage) == 0.0


def test_comment_length_measures_what_the_file_wrote_about_itself() -> None:
    """Measuring one comment reads tokens, characters, or lines against the ceiling it is given.

    One library opened all 206 of its files with the same notice and failed on every one.
    Measuring it says how long the licence is, so the notice is left out and whatever the file
    actually wrote about itself is what gets measured.
    """
    group_span = SourceSpan(path="project", start_line=4, end_line=5)
    subject = comment(
        CommentGroup(
            line_count=2,
            character_count=100,
            token_count=40,
            node=NodeRef(id="project:4:comment", span=group_span, kind="comment"),
        )
    )
    answer = retained_query(subject, comment_length, measure="tokens", normalization_max=200)
    findings = answer.findings

    assert findings is not None
    rows = findings.rows.collect()
    assert (
        query_value(answer),
        rows.item(0, "message"),
        rows.item(0, "path"),
        rows.item(0, "start_line"),
        rows.item(0, "end_line"),
        dict(
            zip(
                rows.item(0, "measurement_names"),
                rows.item(0, "measurement_values"),
                strict=True,
            )
        ),
        rows.item(0, "choice_question"),
        value(subject, comment_length, measure="characters", normalization_max=400),
        value(subject, comment_length, measure="lines", normalization_max=20),
        value(subject, comment_length, measure="tokens", normalization_max=20),
    ) == (
        20.0,
        "the largest comment group spans 40 tokens, which is 20 percent of the 200 tokens used "
        "as the normalization maximum",
        group_span.path,
        group_span.start_line,
        group_span.end_line,
        {
            "tokens in the comment group": 40,
            "tokens at the normalization maximum": 200,
            "normalized comment length": 20.0,
        },
        "",
        25.0,
        10.0,
        100.0,
    )


def test_comment_length_ignores_license_notices() -> None:
    """A license header does not become the file's own implementation comment."""
    notice = CommentGroup(
        line_count=15,
        character_count=900,
        token_count=180,
        node=NodeRef(
            id="a.cuh:0:comment",
            span=_SPAN,
            kind="comment",
            text="""/*
 * Copyright (c) 2026, NVIDIA CORPORATION.
 * Licensed under the Apache License, Version 2.0 (the "License");
 */""",
        ),
    )
    licensed = comment(notice, CommentGroup(line_count=1, character_count=40, token_count=20))

    notice_only = retained_query(comment(notice), comment_length)
    assert notice_only.findings is not None
    assert (
        value(licensed, comment_length),
        notice_only.findings.rows.collect().is_empty(),
        value(licensed, comment_length, notice_markers=[]),
    ) == (10.0, True, 90.0)


def test_comment_length_ignores_documentation() -> None:
    """Documentation comments are outside the implementation comment measure."""
    documented = comment(
        CommentGroup(
            line_count=8,
            character_count=900,
            token_count=180,
            is_documentation=True,
        )
    )
    assert value(documented, comment_length) == 0.0


def test_comment_length_empty_and_invalid_cases() -> None:
    subject = CommentFact(key="comment", span=_SPAN)
    assert value(subject, comment_length) == 0.0
    with pytest.raises(ValueError, match="Unsupported comment measure"):
        retained_query(
            subject.model_copy(
                update={"groups": [CommentGroup(line_count=1, character_count=1, token_count=1)]}
            ),
            comment_length,
            measure="words",
        )
    with pytest.raises(ValidationError, match="greater than 0"):
        validated_setting(comment_length.hints["normalization_max"], 0)


def test_project_automation_cases() -> None:
    complete = AutomationTaskFact(
        key="automation",
        span=_SPAN,
        tasks=[
            AutomationTask(capability=name, commands=[f"chefe run {name}"])
            for name in ("setup", "lint", "typecheck", "test", "build")
        ],
    )
    missing = complete.model_copy(update={"tasks": complete.tasks[:-1]})
    ambiguous = complete.model_copy(
        update={
            "tasks": [
                *complete.tasks[:-1],
                AutomationTask(
                    capability="build",
                    commands=["chefe run build", "python -m build"],
                ),
            ]
        }
    )
    interactive = complete.model_copy(
        update={
            "tasks": [
                *complete.tasks[:-1],
                AutomationTask(
                    capability="build",
                    commands=["chefe run build"],
                    is_noninteractive=False,
                ),
            ]
        }
    )

    assert value(complete, project_automation) is False
    assert value(missing, project_automation) is True
    assert value(ambiguous, project_automation) is True
    assert value(interactive, project_automation) is True


def test_alert_and_review_evidence_drives_coverage() -> None:
    """Alert and review coverage derive answers from their retained fields."""
    actionable = AlertDefinition(
        name="latency",
        condition="p99 latency above budget",
        severity="critical",
        impact="checkout delayed",
        owner="payments",
        destination="pager",
        action="inspect dependency latency",
        runbook="runbooks/latency.md",
    )
    unactionable = actionable.model_copy(update={"runbook": ""})
    alerts = AlertFact(key="alerts", span=_SPAN, alerts=[actionable, unactionable])
    assert value(alerts, alert_actionability) == 50.0

    reviewed = ChangeRecord(
        identifier="change-1",
        author="pedro",
        approvals=[ChangeApproval(reviewer="alice")],
    )
    self_approved = ChangeRecord(
        identifier="change-2",
        author="pedro",
        approvals=[ChangeApproval(reviewer="pedro")],
    )
    changes = ChangeFact(key="changes", span=_SPAN, changes=[reviewed, self_approved])
    assert value(changes, review_coverage) == 50.0


def test_onboarding_and_budget_evidence_drives_coverage() -> None:
    """Onboarding and budget coverage derive answers from their retained fields."""
    onboarding = AutomationTaskFact(
        key="onboarding",
        span=_SPAN,
        tasks=[
            AutomationTask(
                capability="setup",
                commands=["chefe run setup"],
                guidance_locations=["README.md"],
            ),
            AutomationTask(capability="test", commands=["chefe run test"]),
        ],
    )
    assert (
        value(
            onboarding,
            onboarding_readiness,
            required_capabilities=["setup", "test"],
        )
        == 50.0
    )

    protected = PerformanceBudget(
        name="request latency",
        limit=200,
        unit="milliseconds",
        workload="checkout",
        environment="production-like",
        baseline="main",
        variance_policy="five percent",
        check_command="chefe run benchmark",
        owner="performance",
        last_outcome="passed",
    )
    partial = PerformanceBudget(name="memory", check_command="chefe run benchmark")
    budgets = PerformanceDecisionFact(
        key="budgets",
        span=_SPAN,
        budgets=[protected, partial],
    )
    assert value(budgets, regression_guard_coverage) == 50.0


def test_raw_policy_coverage_is_all_or_nothing_per_record() -> None:
    """One record counts only when its raw fields satisfy the whole rule-owned predicate."""
    complete = ServiceObjective(
        name="api",
        owner="platform",
        user_journeys=["checkout"],
        indicators=["availability"],
        objectives=["99.9 percent"],
        windows=["thirty days"],
        error_budget_policy="stop releases when exhausted",
    )
    objectives = ServiceObjectiveFact(key="services", span=_SPAN, services=[complete])
    assert value(objectives, service_objective_coverage) == 100.0
    partial = ServiceObjectiveFact(
        key="services",
        span=_SPAN,
        services=[ServiceObjective(name="api", owner="platform")],
    )
    assert value(partial, service_objective_coverage) == 0.0

    verified = RunbookFact(
        key="runbooks",
        span=_SPAN,
        triggers=[
            RunbookTrigger(
                name="database outage",
                owner="database",
                commands=["chefe run recover"],
                verification_age_days=5,
            )
        ],
    )
    assert value(verified, runbook_coverage) == 100.0
    assert value(RunbookFact(key="runbooks", span=_SPAN), runbook_coverage) == 0.0
