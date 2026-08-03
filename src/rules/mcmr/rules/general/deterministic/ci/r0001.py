from typing import Literal

import polars as pl

from ..... import Category, rule
from .....facts import CIConfigurationFact
from .....query import FindingQuery, RuleQuery
from .....table import Table


@rule(
    "ALL-CI0001",
    policy=Category(good={"complete"}, neutral={"partial"}, bad={"fragile", "absent"}),
)
def continuous_integration(
    subject: Table[CIConfigurationFact],
    *,
    required_tasks: tuple[str, ...] = ("lint", "typecheck", "test"),
) -> RuleQuery[Literal["complete", "partial", "fragile", "absent"]]:
    """Assess whether continuous integration enforces required gates.

    Definition
    ----------
    Inspect workflow triggers, required tasks, supported runtimes, dependency locking,
    cancellation, permissions, and branch protection from the selected in-memory fact provider.
    The engine skips the rule when no provider can build this family because missing evidence does
    not prove that the repository has no continuous integration.

    Evidence
    --------
    Findings retain workflows, triggers, commands, environments, and missing gates.

    Exceptions
    ----------
    A pre-release prototype can accept partial automation through explicit project policy. An
    Explicit evidence with no gates classifies CI as absent. No evidence leaves the rule
    unassessed. `required_tasks` names the gates a change has to pass, defaulting to lint,
    typecheck, and test, so a project that spells its gates differently states its own.

    Examples
    --------
    A pull request workflow running lint, types, and tests is `complete` for those gates. A
    manually triggered test workflow is `partial` protection.

    References
    ----------
    Cites "Software Engineering at Google", Continuous Integration
    Cites "GitHub Actions documentation"
    Cites "OpenSSF Scorecard", CI tests
    """
    relations = subject
    blocking = relations.records("workflows").filter(pl.col("is_change_blocking"))
    protected = (
        relations.values("workflows.tasks")
        .filter(pl.col("string_value").is_in(required_tasks))
        .join(
            blocking.select(
                "fact_id",
                pl.col("record_id").alias("workflow_id"),
                (
                    pl.col("uses_locked_dependencies")
                    & pl.col("has_explicit_permissions")
                    & pl.col("cancels_superseded_runs")
                ).alias("robust"),
            ),
            left_on=["fact_id", "parent_id"],
            right_on=["fact_id", "workflow_id"],
            how="inner",
        )
    )
    summary = protected.group_by("fact_id", maintain_order=True).agg(
        pl.col("string_value").n_unique().alias("present"),
        pl.col("robust").all().alias("robust"),
    )
    facts = (
        relations.facts()
        .join(summary, on="fact_id", how="left")
        .with_columns(
            pl.col("present").fill_null(0),
            pl.col("robust").fill_null(False),
        )
        .with_columns(
            pl.when((pl.col("present") == 0) | pl.lit(not required_tasks))
            .then(pl.lit("absent"))
            .when(pl.col("present") < len(required_tasks))
            .then(pl.lit("partial"))
            .when(pl.col("robust"))
            .then(pl.lit("complete"))
            .otherwise(pl.lit("fragile"))
            .alias("value")
        )
    )
    return RuleQuery.category(
        facts,
        pl.col("value"),
        findings=FindingQuery.precise_category(
            facts,
            pl.col("value"),
            "continuous integration",
            evidence=pl.col("evidence"),
        ),
    )
