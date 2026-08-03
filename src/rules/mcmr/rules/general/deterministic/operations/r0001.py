import polars as pl
from pydantic import NonNegativeInt

from ..... import Numeric, rule
from .....domain.contracts import Unit
from .....facts import RunbookFact
from .....query import FindingQuery, PercentageQuery, RuleQuery
from .....table import Table


@rule("ALL-OPER0001", policy=Numeric(minimum=95))
def runbook_coverage(
    subject: Table[RunbookFact],
    *,
    maximum_age_days: NonNegativeInt = 90,
) -> PercentageQuery:
    """Measure operational triggers linked to current executable guidance.

    Definition
    ----------
    Divide in-scope alerts, manual operations, and recovery scenarios with owned and recently
    verified runbooks by all in-scope triggers and return the percentage.

    Evidence
    --------
    Findings retain trigger, runbook, owner, prerequisites, commands, verification, and age. The
    value is the percentage of in-scope triggers carrying an owned and recently verified runbook.

    Exceptions
    ----------
    Fully automated self-healing paths may link to design evidence instead. `maximum_age_days`
    states how recently an ordinary runbook must have been exercised.

    Examples
    --------
    Nine covered triggers among ten produce `90`. A stale document naming removed commands does
    not count as verified guidance.

    References
    ----------
    Cites "Site Reliability Engineering", effective troubleshooting
    Cites "The Site Reliability Workbook", on-call and incident response
    Cites "Incident Management for Operations", runbook practices
    """
    relations = subject
    triggers = relations.records("triggers").filter(pl.col("in_scope"))
    ordinary = pl.all_horizontal(
        pl.col("owner").str.strip_chars() != "",
        pl.col("commands.length") > 0,
        pl.col("verification_age_days") <= maximum_age_days,
    ).fill_null(False)
    self_healing = pl.col("self_healing") & (pl.col("design_evidence").str.strip_chars() != "")
    facts = relations.coverage(triggers, ordinary | self_healing)
    return RuleQuery.floating(
        facts,
        pl.col("value"),
        findings=FindingQuery.precise_float(
            facts,
            pl.col("value"),
            "runbook coverage",
            Unit.PERCENTAGE,
            evidence=pl.col("evidence"),
        ),
    )
