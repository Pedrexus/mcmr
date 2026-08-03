import polars as pl

from ..... import rule
from .....domain.contracts import FixSafety
from .....facts import TryBlockFact
from .....query import CountQuery, FindingQuery, FixQuery, RuleQuery
from .....table import Table


@rule("PY-EXCE0001", fix_safety=FixSafety.SAFE)
def broad_try_literal_setup(subject: Table[TryBlockFact]) -> CountQuery:
    """Count literal local setup assignments needlessly protected by a broad `try`.

    Definition
    ----------
    Inspect ordinary `try` statements inside functions. Report a `try` when its body starts with
    one or more assignments of a literal `ast.Constant` to one simple local name, another body
    statement follows, and that next statement contains an explicit operation that can raise.
    Calls, imports, attribute or subscript access, arithmetic, comparison, assertion, raising,
    iteration, context management, and awaiting are the exact protected-operation set. Moving the
    literal assignments immediately before the `try` narrows which failures the handlers catch.

    Evidence
    --------
    Each finding identifies every movable local name, the exact source range of the leading setup,
    and the first protected operation. No automatic edit is offered because comments and the
    indentation of a compound statement require a concrete-syntax transformation. The value is the
    number of `try` regions opening with movable literal setup.

    Exceptions
    ----------
    Abstain at module or class scope, for `try` statements with `finally`, for exception-group
    `try*`, and when a candidate name is declared `global` or `nonlocal`. Annotated, chained,
    destructuring, attribute, subscript, computed, or type-commented assignments are not proven
    non-raising. A `try` containing only literal setup and a non-raising return is not reported.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       try:
           mode = "rb"
           payload = stream.read()
       except OSError:
           recover()

    Good
    ~~~~
    .. code-block:: python

       mode = "rb"
       try:
           payload = stream.read()
       except OSError:
           recover()

    Keep a computed setup expression inside when evaluating it belongs to the recovery boundary.

    References
    ----------
    Cites "The Python Tutorial", Handling Exceptions
    https://docs.python.org/3.14/tutorial/errors.html#handling-exceptions
    Cites "The Python Language Reference", the try statement
    https://docs.python.org/3.14/reference/compound_stmts.html#the-try-statement
    Cites "Clean Code in Python", Error Handling
    """
    relations = subject
    regions = relations.records("regions")
    selected = regions.filter(
        (pl.col("leading_literal_assignment_count") > 0)
        & pl.col("has_following_raising_operation")
    )
    frame = relations.counted(selected)
    eligible_regions = regions.filter(
        pl.col("statement.id").is_not_null() & pl.col("has_following_raising_operation")
    ).select(
        "fact_id",
        pl.col("record_id").alias("region_id"),
        pl.col("ordinal").alias("region_order"),
        "statement.id",
        "statement.kind",
        "statement.text",
        "statement.span.path",
        "statement.span.start_line",
        "statement.span.start_column",
        "statement.span.end_line",
        "statement.span.end_column",
    )
    fixable = (
        relations.records("regions.leading_assignments")
        .select(
            "fact_order",
            "fact_id",
            "parent_id",
            pl.col("ordinal").alias("assignment_order"),
            "id",
            "kind",
            "text",
            "span.path",
            "span.start_line",
            "span.start_column",
            "span.end_line",
            "span.end_column",
        )
        .join(
            eligible_regions,
            left_on=["fact_id", "parent_id"],
            right_on=["fact_id", "region_id"],
            how="inner",
        )
        .sort("fact_order", "region_order", "assignment_order")
        .with_row_index("rewrite_order")
        .with_columns(pl.col("rewrite_order").cast(pl.UInt64))
    )
    rewrites = fixable.select(
        "fact_id",
        "rewrite_order",
        pl.lit("move").alias("kind"),
        pl.lit("").alias("source"),
        pl.lit("before").alias("placement"),
        pl.lit("").alias("name"),
        pl.lit("").alias("symbol_id"),
        pl.lit("").alias("symbol_name"),
        pl.lit(False).alias("references_complete"),
    )
    nodes = pl.concat(
        [
            fixable.select(
                "fact_id",
                "rewrite_order",
                pl.lit("target").alias("role"),
                pl.lit(0, dtype=pl.UInt64).alias("ordinal"),
                "id",
                pl.col("span.path").alias("path"),
                pl.col("span.start_line").cast(pl.UInt64).alias("start_line"),
                pl.col("span.start_column").cast(pl.UInt64).alias("start_column"),
                pl.col("span.end_line").cast(pl.UInt64).alias("end_line"),
                pl.col("span.end_column").cast(pl.UInt64).alias("end_column"),
                "kind",
                "text",
            ),
            fixable.select(
                "fact_id",
                "rewrite_order",
                pl.lit("anchor").alias("role"),
                pl.lit(0, dtype=pl.UInt64).alias("ordinal"),
                pl.col("statement.id").alias("id"),
                pl.col("statement.span.path").alias("path"),
                pl.col("statement.span.start_line").cast(pl.UInt64).alias("start_line"),
                pl.col("statement.span.start_column").cast(pl.UInt64).alias("start_column"),
                pl.col("statement.span.end_line").cast(pl.UInt64).alias("end_line"),
                pl.col("statement.span.end_column").cast(pl.UInt64).alias("end_column"),
                pl.col("statement.kind").alias("kind"),
                pl.col("statement.text").alias("text"),
            ),
        ]
    )
    return RuleQuery.integer(
        frame,
        pl.col("value"),
        findings=FindingQuery.precise_integer(
            frame,
            pl.col("value"),
            "broad try literal setup",
            evidence=pl.col("evidence"),
        ),
        fix=FixQuery.build(
            "Lift the literal setup above the statement that protects it.",
            rewrites=rewrites,
            nodes=nodes,
        ),
    )
