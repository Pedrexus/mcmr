import polars as pl

from ..... import Numeric, rule
from .....domain.contracts import Unit
from .....facts import PerformanceDecisionFact
from .....query import FindingQuery, PercentageQuery, RuleQuery
from .....table import Table


@rule("ALL-PERF0001", policy=Numeric(minimum=95))
def regression_guard_coverage(
    subject: Table[PerformanceDecisionFact],
) -> PercentageQuery:
    """Measure critical performance budgets protected by repeatable regression checks.

    Definition
    ----------
    Divide declared critical performance budgets with a numeric limit, workload, environment,
    controlled baseline, variance policy, owned check command, and retained outcome by all
    declared critical budgets and return the percentage.

    Evidence
    --------
    Findings retain budget, workload, environment, baseline, variance policy, and check outcome.
    The value is the percentage of critical budgets protected by a repeatable regression check.

    Exceptions
    ----------
    Expensive system benchmarks may run asynchronously when regressions still have an owned gate.

    Examples
    --------
    Nine protected budgets among ten produce `90`. A benchmark with no baseline or variance policy
    does not count as a regression guard.

    References
    ----------
    Cites "Systems Performance"
    Cites "pytest-benchmark documentation"
    Cites "Google Benchmark documentation"
    """
    relations = subject
    budgets = relations.records("budgets").filter(pl.col("critical"))
    complete = pl.all_horizontal(
        pl.col("limit").is_not_null(),
        *(
            pl.col(field).str.strip_chars() != ""
            for field in (
                "unit",
                "workload",
                "environment",
                "baseline",
                "variance_policy",
                "check_command",
                "owner",
                "last_outcome",
            )
        ),
    )
    facts = relations.coverage(budgets, complete)
    return RuleQuery.floating(
        facts,
        pl.col("value"),
        findings=FindingQuery.precise_float(
            facts,
            pl.col("value"),
            "regression guard coverage",
            Unit.PERCENTAGE,
            evidence=pl.col("evidence"),
        ),
    )
