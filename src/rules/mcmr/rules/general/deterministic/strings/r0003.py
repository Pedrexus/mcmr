import polars as pl
from pydantic import NonNegativeInt

from ..... import rule
from .....domain.contracts import Unit
from .....facts import StringExpressionFact
from .....query import CountQuery, FindingQuery, RuleQuery
from .....table import Table


@rule("ALL-STRI0002")
def decorative_repeated_separator_count(
    subject: Table[StringExpressionFact], *, minimum_repetitions: NonNegativeInt = 3
) -> CountQuery:
    """Find fixed repeated-string expressions used as decorative separators.

    Definition
    ----------
    Report multiplication of a nonempty punctuation-only string literal by a fixed integer at or
    above `minimum_repetitions`. Recognize either operand order and a conservative set of common
    separator characters. Prefer a semantic heading, structured logger field, or natural spacing
    instead of manufacturing a visual rule whose width carries no program meaning.

    Evidence
    --------
    Each finding records the expression range, separator literal, and fixed repetition count. The
    value is the number of decorative separator expressions.

    Exceptions
    ----------
    Alphanumeric strings, whitespace, control bytes, variable counts, and repetitions below the
    threshold are excluded because they may encode data, padding, or a protocol requirement.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       logger.info("-" * 30)
       banner = 12 * "="

    Good
    ~~~~
    .. code-block:: python

       logger.info("Dependency checks")
       padding = "0" * width

    References
    ----------
    Cites "The Python Language Reference", binary arithmetic operations and sequence repetition
    https://docs.python.org/3/reference/expressions.html#binary-arithmetic-operations
    Cites "Python HOWTOs", structured contextual logging
    https://docs.python.org/3/howto/logging-cookbook.html
    """
    relations = subject
    selected = relations.records("expressions").filter(
        (pl.col("kind") == "fixed-repetition")
        & pl.col("literal").str.contains(r"^[-_*=~.#]+$")
        & (pl.col("repetition_count") >= minimum_repetitions)
    )
    frame = relations.counted(selected)
    finding_rows = selected.join(
        relations.facts().select("fact_id", "evidence"),
        on="fact_id",
        how="inner",
    ).with_columns(
        pl.col("node.span.path").alias("path"),
        pl.col("node.span.start_line").alias("start_line"),
        pl.col("node.span.start_column").alias("start_column"),
        pl.col("node.span.end_line").alias("end_line"),
        pl.col("node.span.end_column").alias("end_column"),
    )
    return RuleQuery.integer(
        frame,
        pl.col("value"),
        findings=FindingQuery.build(
            finding_rows,
            pl.concat_str(
                pl.lit("Decorative separator repeats `"),
                pl.col("literal"),
                pl.lit("` "),
                pl.col("repetition_count"),
                pl.lit(" times"),
            ),
            (("decorative repeated separator count", pl.lit(1), Unit.COUNT),),
            finding_order=pl.col("ordinal"),
            evidence=pl.col("evidence"),
        ),
    )
