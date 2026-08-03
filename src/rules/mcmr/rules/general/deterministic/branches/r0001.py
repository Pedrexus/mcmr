import polars as pl
from pydantic import NonNegativeInt

from ..... import rule
from .....domain.contracts import Unit
from .....facts import BranchFact
from .....query import CountQuery, FindingQuery, RuleQuery
from .....table import Table


@rule("ALL-BRAN0001")
def value_dispatch_candidate(
    subject: Table[BranchFact], *, minimum_arms: NonNegativeInt = 3
) -> CountQuery:
    """Count condition chains that only select behavior by one value.

    Definition
    ----------
    Report a chain of `minimum_arms` or more arms where every arm compares the same subject against
    a distinct literal and reads nothing else. Such a chain is a lookup written as control flow.
    Every new case edits the same function, which is exactly the change a dispatch table, a match
    over a closed type, or a registry avoids. The rule reports the chain, not the individual arms,
    because the chain is what gets replaced.

    Evidence
    --------
    Each finding records the chain range, the subject, every literal it tests, and whether a
    fallback arm exists. The value is the number of chains.

    Exceptions
    ----------
    A chain whose arms test different subjects, compare with anything other than equality, or read
    additional state is real branching logic and is not counted. A chain of two arms is left alone
    because a table costs more than it saves at that size.

    Examples
    --------
    Three arms testing `kind == "pbs"`, `kind == "slurm"`, and `kind == "ssh"`, with or without a
    fallback beneath them, return `1` and should become a registry or a mapping. A chain testing
    `kind == "pbs"` and then `queue.is_full` returns `0`, because its second arm reads something
    else. A chain testing `kind == "pbs"` twice returns `0` as well, since two arms share one
    literal.

    References
    ----------
    Cites "Refactoring", replace conditional with polymorphism
    Cites Clippy match_like_matches_macro
    Cites Clippy comparison_chain
    https://rust-lang.github.io/rust-clippy/master/index.html#comparison_chain
    Cites "The Python Standard Library", `functools.singledispatch` and structural pattern matching
    https://docs.python.org/3/library/functools.html#functools.singledispatch
    """
    relations = subject
    arms = relations.records("chains.arms")
    qualified = arms.group_by("fact_id", "parent_id", maintain_order=True).agg(
        pl.len().alias("arm_count"),
        (pl.col("reads_subject_only") & (pl.col("literal") != "")).all().alias("valid"),
        pl.col("literal").n_unique().alias("distinct_literals"),
        pl.col("literal").sort_by("ordinal").alias("literals"),
    )
    selected = (
        relations.records("chains")
        .join(
            qualified,
            left_on=["fact_id", "record_id"],
            right_on=["fact_id", "parent_id"],
            how="inner",
        )
        .filter(
            (pl.col("arm_count") >= minimum_arms)
            & (pl.col("subject") != "")
            & pl.col("valid")
            & (pl.col("distinct_literals") == pl.col("arm_count"))
        )
        .with_columns(
            pl.col("node.span.path").alias("path"),
            pl.col("node.span.start_line").alias("start_line"),
            pl.col("node.span.start_column").alias("start_column"),
            pl.col("node.span.end_line").alias("end_line"),
            pl.col("node.span.end_column").alias("end_column"),
        )
        .join(
            relations.facts().select("fact_id", "evidence"),
            on="fact_id",
            how="inner",
        )
    )
    facts = relations.counted(selected)
    return RuleQuery.integer(
        facts,
        pl.col("value"),
        findings=FindingQuery.build(
            selected,
            pl.concat_str(
                pl.lit("`"),
                pl.col("subject"),
                pl.lit("` selects among "),
                pl.col("arm_count"),
                pl.lit(" literal arms `"),
                pl.col("literals").list.join("`, `"),
                pl.lit("`"),
            ),
            (("value dispatch candidate", pl.lit(1), Unit.COUNT),),
            finding_order=pl.col("ordinal"),
            evidence=pl.col("evidence"),
        ),
    )
