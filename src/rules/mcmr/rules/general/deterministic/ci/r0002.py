import polars as pl
from pydantic import NonNegativeInt

from ..... import Numeric, rule
from .....domain.contracts import Unit
from .....facts import CICheckFact, Ratio
from .....query import FindingQuery, PercentageQuery, RuleQuery
from .....table import Table


@rule("ALL-CI0002", policy=Numeric(minimum=95))
def feedback_target_coverage(
    subject: Table[CICheckFact], *, target_seconds: NonNegativeInt = 600, percentile: Ratio = 0.9
) -> PercentageQuery:
    """Measure required CI checks meeting the configured feedback target.

    Definition
    ----------
    For each required check, compare its configured duration percentile with the feedback target.
    Return the percentage of required checks that meet the target.

    Evidence
    --------
    Findings retain workflow, check, duration distribution, queue time, and target. The value is
    the percentage of required change-blocking checks meeting the feedback target.

    Exceptions
    ----------
    Explicit asynchronous qualification suites may run outside the change-blocking feedback path.
    `target_seconds` is the feedback target a required check has to meet and `percentile` chooses
    which point of its duration distribution is compared, so a project judging its slowest runs
    raises the percentile rather than the target.

    Examples
    --------
    Nine of ten required checks meeting a ten-minute target produce `90`. A nightly soak test does
    not enter the denominator unless it blocks ordinary changes.

    References
    ----------
    Cites "Software Engineering at Google", Continuous Integration
    Cites "Accelerate", fast feedback and continuous delivery
    Cites "DORA research", continuous delivery
    """
    relations = subject
    required = relations.records("checks").filter(
        pl.col("is_required") & pl.col("is_change_blocking") & (pl.col("percentile") >= percentile)
    )
    summary = required.group_by("fact_id", maintain_order=True).agg(
        pl.len().alias("required"),
        (pl.col("duration_percentile_seconds") <= target_seconds).sum().alias("passing"),
    )
    facts = (
        relations.facts()
        .join(summary, on="fact_id", how="left")
        .with_columns(
            pl.col("required").fill_null(0),
            pl.col("passing").fill_null(0),
        )
        .with_columns(
            pl.when(pl.col("required") == 0)
            .then(0.0)
            .otherwise(pl.col("passing") / pl.col("required") * 100.0)
            .alias("value")
        )
    )
    return RuleQuery.floating(
        facts,
        pl.col("value"),
        findings=FindingQuery.precise_float(
            facts,
            pl.col("value"),
            "feedback target coverage",
            Unit.PERCENTAGE,
            evidence=pl.col("evidence"),
        ),
    )
