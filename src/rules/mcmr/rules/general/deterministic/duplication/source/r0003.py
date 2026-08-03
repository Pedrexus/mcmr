import polars as pl
from pydantic import PositiveInt

from ...... import Numeric, rule
from ......domain.contracts import Unit
from ......facts import CloneGroupFact, DetectableCloneTokenCount
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import Table
from ..relations import CloneTables


@rule("ALL-DUPL0003", policy=Numeric())
def pasted_block_copy_count(
    subject: Table[CloneGroupFact],
    *,
    minimum_token_length: DetectableCloneTokenCount = 60,
    minimum_line_count: PositiveInt = 4,
) -> CountQuery:
    """Count repeated normalized implementation blocks.

    Definition
    ----------
    Measure one group of fragments the kernel matched on normalized tokens, where every identifier
    became a placeholder and every literal became a placeholder for its kind, so a copy is still a
    copy after its locals were renamed and its formatting was redone. Report the copies past the
    first when the repeated run reaches `minimum_token_length` normalized tokens and covers at
    least `minimum_line_count` lines. The value is the number of copies after the first. The
    comparison survives cosmetic edits while remaining tied to one exact executable source range.
    Whether two matches share knowledge is left to `ALL-DUPL1001` or an explicit project ceiling.

    The kernel admits implementation blocks from forty normalized tokens so it can retain compact
    pasted bodies. This rule defaults to sixty before calling one a defect, while four lines is
    what Symilar asks for by default. Raising the token floor is the honest way to ask for fewer
    findings, because the cost of matching on shape is that short pieces of implementation can
    look alike without sharing knowledge. A setting below forty is refused because the provider
    cannot supply complete evidence in that domain.

    Evidence
    --------
    One finding is stated per copy past the first, each located at that copy and naming the lines
    the original covers, so the number of findings and the value are the same number read two
    ways. Each carries how many lines and how many tokens the block runs to, and the repair is a
    choice, because two blocks that look alike are not always the same idea.

    Exceptions
    ----------
    A run under either floor is not reported at all, because normalization deliberately throws
    away every name and every literal and short runs of shape are ordinary rather than copied. A
    group whose copies all sit inside a longer group is never built, so a long paste is one
    finding rather than one for each of the shorter readings inside it. Whether the copies should
    be merged is a judgment about shared knowledge that this rule does not make, and
    `ALL-DUPL1001` reads the very same fact to make it.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       def total_over(rows, limit):
           total = 0
           for row in rows:
               total = total + row.value if row.value > limit else total
           return total

       def sum_above(items, floor):
           carried = 0
           for item in items:
               carried = carried + item.value if item.value > floor else carried
           return carried

    Good
    ~~~~
    .. code-block:: python

       def total_over(rows, limit):
           return sum(row.value for row in rows if row.value > limit)

    References
    ----------
    Generalizes Pylint R0801 duplicate-code
    Cites "The Pragmatic Programmer", the DRY principle
    Cites "Refactoring", Extract Function
    https://refactoring.com/catalog/extractFunction.html
    """
    relations = CloneTables(subject)
    qualified = (pl.col("token_length") >= minimum_token_length) & (
        pl.col("line_count") >= minimum_line_count
    )
    frame = relations.groups().with_columns(
        pl.when(qualified)
        .then(pl.col("copy_count") - 1)
        .otherwise(pl.lit(0, dtype=pl.UInt64))
        .alias("value")
    )
    originals = (
        relations.fragments()
        .filter(pl.col("ordinal") == 0)
        .select(
            "fact_id",
            pl.col("path").alias("original_path"),
            pl.col("start_line").alias("original_start_line"),
            pl.col("end_line").alias("original_end_line"),
        )
    )
    selected = (
        relations.fragments()
        .filter(pl.col("ordinal") > 0)
        .join(
            frame.filter(qualified).select("fact_id", "token_length", "copy_count"),
            on="fact_id",
            how="inner",
        )
        .join(originals, on="fact_id", how="inner")
        .with_columns(
            (pl.col("end_line") - pl.col("start_line") + 1)
            .cast(pl.UInt64)
            .alias("copy_line_count"),
            (pl.col("ordinal") - 1).cast(pl.UInt64).alias("finding_order"),
        )
    )
    findings = FindingQuery.build(
        selected,
        pl.concat_str(
            pl.lit("this implementation spans "),
            pl.col("copy_line_count"),
            pl.when(pl.col("copy_line_count") == 1)
            .then(pl.lit(" line"))
            .otherwise(pl.lit(" lines")),
            pl.lit(" and matches the same "),
            pl.col("token_length"),
            pl.lit("-token normalized structure as `"),
            pl.col("original_path"),
            pl.lit("` at lines "),
            pl.col("original_start_line"),
            pl.lit(" to "),
            pl.col("original_end_line"),
        ),
        (
            ("repeated lines", pl.col("copy_line_count"), Unit.COUNT),
            ("tokens in the block", pl.col("token_length"), Unit.COUNT),
            ("copies of it in the tree", pl.col("copy_count"), Unit.COUNT),
        ),
        finding_order=pl.col("finding_order"),
        question="name this block once and call it from both places",
        options=(
            "extract it where the two copies mean the same thing",
            "let them diverge where they only look alike",
        ),
    )
    return RuleQuery.integer(frame, pl.col("value"), findings=findings)
