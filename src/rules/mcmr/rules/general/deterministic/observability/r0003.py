import polars as pl

from ..... import Numeric, rule
from .....domain.contracts import Unit
from .....facts import AlertFact
from .....query import FindingQuery, PercentageQuery, RuleQuery
from .....table import Table


@rule("ALL-OBSE0002", policy=Numeric(minimum=95))
def alert_actionability(
    subject: Table[AlertFact],
) -> PercentageQuery:
    """Measure alerts with enough information for an owned response.

    Definition
    ----------
    Divide enabled paging alerts that meet every configured actionability field by all enabled
    paging alerts and return the percentage.

    Evidence
    --------
    Findings retain alert condition, impact, owner, destination, runbook, and recent outcomes. The
    value is the percentage of enabled paging alerts meeting every actionability field.

    Exceptions
    ----------
    An informational notification stays out of the denominator entirely, since nothing about it is
    supposed to wake anybody and holding it to a paging alert's contract would depress the number
    without improving a response. A disabled alert is excluded for the same reason. An alert that
    names an owner who has since left still counts as owned here, because the roster is evidence
    this rule does not hold.

    Examples
    --------
    Eighteen actionable paging alerts among twenty produce `90`. An alert with no owner or response
    path does not count.

    References
    ----------
    Cites "Site Reliability Engineering", monitoring distributed systems
    Cites "The Site Reliability Workbook", alerting on SLOs
    Cites "Prometheus documentation", alerting best practices
    """
    relations = subject
    alerts = relations.records("alerts").filter(
        pl.col("enabled") & (pl.col("audience") == "paging")
    )
    complete = pl.all_horizontal(
        *(
            pl.col(field).str.strip_chars() != ""
            for field in (
                "condition",
                "severity",
                "impact",
                "owner",
                "destination",
                "action",
                "runbook",
            )
        )
    )
    facts = relations.coverage(alerts, complete)
    return RuleQuery.floating(
        facts,
        pl.col("value"),
        findings=FindingQuery.precise_float(
            facts,
            pl.col("value"),
            "alert actionability",
            Unit.PERCENTAGE,
            evidence=pl.col("evidence"),
        ),
    )
