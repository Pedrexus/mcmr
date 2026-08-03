import polars as pl
from pydantic import NonNegativeInt

from ..... import rule
from .....facts import WaiverFact
from .....query import CountQuery, FindingQuery, RuleQuery
from .....table import Table


@rule("ALL-WAIV0001")
def waiver_debt(
    subject: Table[WaiverFact],
    *,
    required_metadata: tuple[str, ...] = ("reason",),
    maximum_age_days: NonNegativeInt = 90,
) -> CountQuery:
    """Count quality waivers that lack a current bounded justification.

    Definition
    ----------
    Count inline lint, typing, coverage, security, architecture, and MCMR suppressions that are
    expired, older than the configured age, overly broad, missing a creation date, or missing
    configured metadata. The rule judges waiver hygiene rather than repeating the diagnostic. A
    waiver justifies itself where it is written, so its age comes from a `since` field and its
    expiry from an `expires` field, each written as an ISO date on the suppression line itself.

    Evidence
    --------
    Findings retain the waiver kind, scope, available structured metadata, age problem, and source
    location. Metadata is a run of `key=value` fields written after the marker, each value running
    to the next field name, so a reason may hold spaces without being quoted.

    Exceptions
    ----------
    Permanent third-party compatibility gaps may remain when narrowly scoped and supported by a
    current upstream reference. Repository Git ignores decide which source files exist before
    this rule runs. `required_metadata` names the fields a suppression comment has to carry,
    defaulting to a reason, and `maximum_age_days` is how long one may live before it counts as
    debt.

    Examples
    --------
    Two blanket ignores and one expired security waiver produce `3`. A narrow, dated suppression
    with a reason does not count. A permanent compatibility waiver also needs an upstream URL.

    References
    ----------
    Generalizes Ruff PGH004 blanket-noqa
    Generalizes Ruff PGH003 blanket-type-ignore
    Cites "OpenSSF Scorecard", dangerous workflow and token permission checks
    """
    relations = subject
    metadata = (
        relations.values("waivers.metadata")
        .filter(
            pl.col("map_key").is_in(required_metadata)
            & (pl.col("string_value").str.strip_chars() != "")
        )
        .group_by("fact_id", "parent_id", maintain_order=True)
        .agg(pl.col("map_key").n_unique().alias("metadata_count"))
    )
    selected = (
        relations.records("waivers")
        .join(
            metadata,
            left_on=["fact_id", "record_id"],
            right_on=["fact_id", "parent_id"],
            how="left",
        )
        .with_columns(pl.col("metadata_count").fill_null(0))
        .filter(
            pl.col("age_days").is_null()
            | (pl.col("age_days") > maximum_age_days)
            | (pl.col("expires_in_days").is_not_null() & (pl.col("expires_in_days") < 0))
            | pl.col("is_overly_broad")
            | (pl.col("metadata_count") < len(set(required_metadata)))
        )
    )
    facts = relations.counted(selected)
    return RuleQuery.integer(
        facts,
        pl.col("value"),
        findings=FindingQuery.precise_integer(
            facts,
            pl.col("value"),
            "waiver debt",
            evidence=pl.col("evidence"),
        ),
    )
