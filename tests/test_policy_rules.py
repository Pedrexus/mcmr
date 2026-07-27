import pytest
from pydantic import ValidationError

from mcmr.facts import (
    AlertFact,
    AutomationTask,
    AutomationTaskFact,
    ChangeFact,
    Checklist,
    ChecklistItem,
    CICheck,
    CICheckFact,
    CIConfigurationFact,
    CIWorkflow,
    CommentFact,
    CommentGroup,
    Fact,
    NodeRef,
    OnboardingTaskFact,
    OperationalRiskFact,
    PerformanceDecisionFact,
    RunbookFact,
    SecurityBoundaryFact,
    ServiceObjectiveFact,
    SourceSpan,
)
from mcmr.facts import (
    TestStrategyFact as StrategyFact,
)
from mcmr.rules.general.deterministic.ci.r0001 import continuous_integration
from mcmr.rules.general.deterministic.ci.r0002 import feedback_target_coverage
from mcmr.rules.general.deterministic.comments.r0002 import comment_length
from mcmr.rules.general.deterministic.lifecycle.r0001 import project_automation
from mcmr.rules.general.deterministic.observability.r0001 import observability_coverage
from mcmr.rules.general.deterministic.observability.r0003 import alert_actionability
from mcmr.rules.general.deterministic.observability.r0004 import service_objective_coverage
from mcmr.rules.general.deterministic.onboarding.r0001 import onboarding_readiness
from mcmr.rules.general.deterministic.operations.r0001 import runbook_coverage
from mcmr.rules.general.deterministic.performance.r0003 import regression_guard_coverage
from mcmr.rules.general.deterministic.reviews.r0002 import review_coverage
from mcmr.rules.general.deterministic.security.r0002 import threat_model_coverage
from mcmr.rules.general.deterministic.testing.r0006 import failure_scenario_coverage

SPAN = SourceSpan(path="project")


def item(name: str, *checks: str, is_in_scope: bool = True) -> ChecklistItem:
    """Build one checklist item with the selected observable checks."""
    return ChecklistItem(
        name=name,
        checks={check: True for check in checks},
        is_in_scope=is_in_scope,
    )


def checklist[FactT: Fact](family: type[FactT], field: str, *items: ChecklistItem) -> FactT:
    """Return one fact of the given family holding these items under its own checklist field.

    Nine policy families are the same shape, one fact wrapped around one named checklist, so the
    family and the name of that field are all that varies and the rest is the frame a frontend
    always fills in the same way.
    """
    return family.model_validate({"key": field, "span": SPAN, field: list(items)})


def comment(*groups: CommentGroup) -> CommentFact:
    """Return one comment fact holding the given contiguous groups."""
    return CommentFact(key="comment", span=SPAN, groups=list(groups))


def test_continuous_integration_cases() -> None:
    absent = CIConfigurationFact(key="ci", span=SPAN)
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

    assert continuous_integration(absent) == "absent"
    assert continuous_integration(partial) == "partial"
    assert continuous_integration(complete) == "complete"
    assert continuous_integration(fragile) == "fragile"
    assert continuous_integration(manual) == "absent"


def test_feedback_target_coverage_cases() -> None:
    no_required_checks = CICheckFact(key="ci-checks", span=SPAN)
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

    assert feedback_target_coverage(no_required_checks) == 0.0
    assert feedback_target_coverage(checks) == 50.0
    assert feedback_target_coverage(checks, target_seconds=700) == 100.0
    assert feedback_target_coverage(lower_confidence) == 0.0


def test_comment_length_measures_what_the_file_wrote_about_itself() -> None:
    """Measuring one comment reads tokens, characters, or lines against the ceiling it is given.

    One library opened all 206 of its files with the same notice and failed on every one.
    Measuring it says how long the licence is, so the notice is left out and whatever the file
    actually wrote about itself is what gets measured.
    """
    subject = comment(CommentGroup(line_count=2, character_count=100, token_count=40))
    assert comment_length(subject, measure="tokens", normalization_max=200) == 20.0
    assert comment_length(subject, measure="characters", normalization_max=400) == 25.0
    assert comment_length(subject, measure="lines", normalization_max=20) == 10.0
    assert comment_length(subject, measure="tokens", normalization_max=20) == 100.0

    notice = CommentGroup(
        line_count=15,
        character_count=900,
        token_count=180,
        node=NodeRef(
            id="a.cuh:0:comment",
            span=SPAN,
            kind="comment",
            text="/*\n * Copyright (c) 2026, NVIDIA CORPORATION.\n * Licensed under the Apache "
            'License, Version 2.0 (the "License");\n */',
        ),
    )
    licensed = comment(notice, CommentGroup(line_count=1, character_count=40, token_count=20))

    assert comment_length(licensed) == 10.0
    assert comment_length(comment(notice)) == 0.0
    assert comment_length(licensed, notice_markers=()) == 90.0


def test_comment_length_empty_and_invalid_cases() -> None:
    subject = CommentFact(key="comment", span=SPAN)
    assert comment_length(subject) == 0.0
    with pytest.raises(ValueError, match="Unsupported comment measure"):
        comment_length(
            subject.model_copy(
                update={"groups": [CommentGroup(line_count=1, character_count=1, token_count=1)]}
            ),
            measure="words",
        )
    with pytest.raises(ValidationError, match="greater than 0"):
        comment_length(subject, normalization_max=0)


def test_project_automation_cases() -> None:
    complete = AutomationTaskFact(
        key="automation",
        span=SPAN,
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

    assert not project_automation(complete)
    assert project_automation(missing)
    assert project_automation(ambiguous)
    assert project_automation(interactive)


def test_a_half_covered_checklist_scores_the_share_holding_every_required_check() -> None:
    """Each of these rules answers the percentage of in-scope items holding every check it asks.

    One item of two carrying the whole set is fifty in every family, whatever the family calls
    its checklist. An item declared out of scope is not counted at all, so the risks below score
    off two items rather than three, and a checklist validated once is not wrapped again. An
    empty checklist has nothing to cover and scores nothing.
    """
    risks = checklist(
        OperationalRiskFact,
        "risks",
        item("payments", "actionable_signal"),
        item("email"),
        item("experiment", is_in_scope=False),
    )
    assert observability_coverage(risks) == 50.0
    assert Checklist.from_value(risks.risks) is risks.risks
    assert observability_coverage(checklist(OperationalRiskFact, "risks")) == 0.0

    actionable = item("latency", "owner", "severity", "condition", "action", "runbook")
    unactionable = actionable.model_copy(update={"checks": actionable.checks | {"runbook": False}})
    assert alert_actionability(checklist(AlertFact, "alerts", actionable, unactionable)) == 50.0

    reviewed = item(
        "change 1", "nontrivial", "approved", "eligible_reviewer", "reviewer_is_not_author"
    )
    self_approved = reviewed.model_copy(
        update={"checks": reviewed.checks | {"reviewer_is_not_author": False}}
    )
    assert review_coverage(checklist(ChangeFact, "changes", reviewed, self_approved)) == 50.0

    onboarding = checklist(
        OnboardingTaskFact,
        "capabilities",
        item("setup", "current_command", "concise_guidance"),
        item("test", "current_command"),
    )
    assert onboarding_readiness(onboarding) == 50.0

    budgets = checklist(
        PerformanceDecisionFact,
        "budgets",
        item("request latency", "representative_comparison", "controlled_baseline", "automated"),
        item("memory", "automated"),
    )
    assert regression_guard_coverage(budgets) == 50.0

    failures = checklist(
        StrategyFact,
        "failure_scenarios",
        item("timeout", "exercised", "meaningful_assertion"),
        item("disconnect", "exercised"),
    )
    assert failure_scenario_coverage(failures) == 50.0


def test_a_checklist_missing_one_required_check_covers_nothing() -> None:
    """Coverage is all of the required checks or none of them, never the fraction one item holds.

    A single item carrying the whole set scores a hundred, and dropping one check off that same
    item takes it to zero rather than to most of the way there. An empty checklist reads the same
    way from the other side, since there is nothing in scope to have covered.
    """
    complete = item("api", "owner", "indicators", "objectives", "windows", "error_budget_policy")
    objectives = checklist(ServiceObjectiveFact, "services", complete)
    assert service_objective_coverage(objectives) == 100.0
    partial = checklist(ServiceObjectiveFact, "services", item("api", "owner"))
    assert service_objective_coverage(partial) == 0.0

    verified = item("database outage", "owner", "recent_verification")
    assert runbook_coverage(checklist(RunbookFact, "triggers", verified)) == 100.0
    assert runbook_coverage(checklist(RunbookFact, "triggers")) == 0.0

    required = ("assets", "actors", "threats", "mitigations", "residual_risk", "owner", "review")
    modeled = checklist(SecurityBoundaryFact, "boundaries", item("public API", *required))
    assert threat_model_coverage(modeled) == 100.0
    unreviewed = checklist(SecurityBoundaryFact, "boundaries", item("public API", *required[:-1]))
    assert threat_model_coverage(unreviewed) == 0.0
