import polars as pl

from ..... import Numeric, rule
from .....domain.contracts import Unit
from .....facts import ChangeFact
from .....query import FindingQuery, PercentageQuery, RuleQuery
from .....table import Table


@rule("ALL-REVI0001", policy=Numeric(minimum=95))
def review_coverage(
    subject: Table[ChangeFact],
) -> PercentageQuery:
    """Measure independently reviewed changes on protected development lines.

    Definition
    ----------
    Divide changes whose merge path requires review and that carry an approval from an eligible
    reviewer other than the author by all changes whose merge path requires review.

    Evidence
    --------
    Findings retain change identity, author, reviewers, ownership, approval, and merge path. The
    value is the percentage of in-scope changes approved by an eligible reviewer other than the
    author.

    Exceptions
    ----------
    Emergency changes may follow a documented retrospective review path. Mechanical bot changes
    may use separate verification policy.

    Examples
    --------
    Ninety-five independently reviewed changes among one hundred produce `95`. Self-approval does
    not satisfy independent review.

    References
    ----------
    Cites "Software Engineering at Google", Code Review
    Cites "OpenSSF Scorecard", branch protection checks
    """
    relations = subject
    changes = relations.records("changes").filter(pl.col("review_required"))
    independent = (
        relations.records("changes.approvals")
        .select("fact_id", "parent_id", "reviewer", "approved", "eligible")
        .filter(pl.col("approved") & pl.col("eligible"))
        .join(
            changes.select(
                "fact_id",
                pl.col("record_id").alias("change_id"),
                "author",
            ),
            left_on=["fact_id", "parent_id"],
            right_on=["fact_id", "change_id"],
            how="inner",
        )
        .filter(pl.col("reviewer") != pl.col("author"))
        .group_by("fact_id", "parent_id", maintain_order=True)
        .agg(pl.lit(True).alias("independently_reviewed"))
    )
    population = (
        changes.join(
            independent,
            left_on=["fact_id", "record_id"],
            right_on=["fact_id", "parent_id"],
            how="left",
        )
        .with_columns(pl.col("independently_reviewed").fill_null(False))
        .with_columns(
            (
                pl.col("independently_reviewed")
                | (pl.col("emergency") & (pl.col("retrospective_review").str.strip_chars() != ""))
                | (pl.col("mechanical") & (pl.col("verification_evidence.length") > 0))
            ).alias("complete")
        )
    )
    facts = relations.coverage(population, pl.col("complete"))
    return RuleQuery.floating(
        facts,
        pl.col("value"),
        findings=FindingQuery.precise_float(
            facts,
            pl.col("value"),
            "review coverage",
            Unit.PERCENTAGE,
            evidence=pl.col("evidence"),
        ),
    )
