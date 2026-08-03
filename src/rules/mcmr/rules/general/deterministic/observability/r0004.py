import polars as pl

from ..... import Numeric, rule
from .....domain.contracts import Unit
from .....facts import ServiceObjectiveFact
from .....query import FindingQuery, PercentageQuery, RuleQuery
from .....table import Table


@rule("ALL-OBSE0003", policy=Numeric(minimum=95))
def service_objective_coverage(
    subject: Table[ServiceObjectiveFact],
) -> PercentageQuery:
    """Measure owned user-facing services with defined service objectives.

    Definition
    ----------
    Divide in-scope user-facing services with an owner, indicators, objectives, windows, and error
    budget policy by all in-scope user-facing services and return the percentage.

    Evidence
    --------
    Findings retain service, owner, user journey, indicators, objectives, windows, and policy. The
    value is the percentage of in-scope services carrying a complete objective.

    Exceptions
    ----------
    Offline libraries and internal experiments may use explicit reliability targets instead.

    Examples
    --------
    Four fully specified services among five produce `80`. A dashboard without an objective or
    window does not satisfy the rule.

    References
    ----------
    Cites "Site Reliability Engineering", Service Level Objectives
    Cites "The Site Reliability Workbook", implementing SLOs
    Cites "Observability Engineering", SLOs across the lifecycle
    """
    relations = subject
    services = relations.records("services").filter(pl.col("in_scope") & pl.col("user_facing"))
    complete = pl.all_horizontal(
        pl.col("owner").str.strip_chars() != "",
        pl.col("user_journeys.length") > 0,
        pl.col("indicators.length") > 0,
        pl.col("objectives.length") > 0,
        pl.col("windows.length") > 0,
        pl.col("error_budget_policy").str.strip_chars() != "",
    )
    facts = relations.coverage(services, complete)
    return RuleQuery.floating(
        facts,
        pl.col("value"),
        findings=FindingQuery.precise_float(
            facts,
            pl.col("value"),
            "service objective coverage",
            Unit.PERCENTAGE,
            evidence=pl.col("evidence"),
        ),
    )
