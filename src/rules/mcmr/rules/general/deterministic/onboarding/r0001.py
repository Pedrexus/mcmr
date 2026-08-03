import polars as pl

from ..... import Numeric, rule
from .....domain.contracts import Unit
from .....facts import AutomationTaskFact
from .....query import FindingQuery, PercentageQuery, RuleQuery
from .....table import Table


@rule("ALL-ONBO0001", policy=Numeric(minimum=95))
def onboarding_readiness(
    subject: Table[AutomationTaskFact],
    *,
    required_capabilities: tuple[str, ...] = (
        "setup",
        "test",
        "architecture",
        "debug",
        "contribute",
    ),
) -> PercentageQuery:
    """Measure whether a newcomer can perform essential project work.

    Definition
    ----------
    Verify each required onboarding capability through one current repository-owned,
    noninteractive command and concise guidance, then return the percentage verified.

    Evidence
    --------
    Findings retain the declared command, guidance location, and static portability evidence.
    The value is the percentage of required capabilities verified through a current command.

    Exceptions
    ----------
    Restricted production access is not required when a safe local or staging path exists.
    `required_capabilities` names the work a newcomer must be able to perform. An empty
    requirement set produces full coverage because there is no onboarding obligation to satisfy.

    Examples
    --------
    Four verified capabilities among five produce `80`. Mentioning a stale setup command
    does not satisfy the setup capability.

    References
    ----------
    Cites "Software Engineering at Google", knowledge sharing
    Cites "GitHub documentation", contributing guidelines
    """
    relations = subject
    verified = (
        relations.records("tasks")
        .filter(
            pl.col("capability").is_in(required_capabilities)
            & (pl.col("commands.length") == 1)
            & (pl.col("guidance_locations.length") > 0)
            & pl.col("is_repository_owned")
            & pl.col("is_noninteractive")
        )
        .group_by("fact_id", maintain_order=True)
        .agg(pl.col("capability").n_unique().alias("verified"))
    )
    facts = (
        relations.facts()
        .join(verified, on="fact_id", how="left")
        .with_columns(pl.col("verified").fill_null(0))
    )
    value = (
        pl.lit(100.0)
        if not required_capabilities
        else pl.col("verified") / len(set(required_capabilities)) * 100.0
    )
    facts = facts.with_columns(value.alias("value"))
    return RuleQuery.floating(
        facts,
        pl.col("value"),
        findings=FindingQuery.precise_float(
            facts,
            pl.col("value"),
            "onboarding readiness",
            Unit.PERCENTAGE,
            evidence=pl.col("evidence"),
        ),
    )
