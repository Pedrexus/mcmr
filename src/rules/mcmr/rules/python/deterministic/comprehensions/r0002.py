import polars as pl

from ..... import Numeric, rule
from .....facts import ComprehensionFact
from .....query import CountQuery, FindingQuery, RuleQuery
from .....table import Table


@rule("PY-COMP0001", policy=Numeric(maximum=2))
def comprehension_loop_count(
    subject: Table[ComprehensionFact],
) -> CountQuery:
    """Measure the largest number of loops in one comprehension.

    Definition
    ----------
    Count the `for` and `async for` clauses of every list, dictionary, set, and generator
    comprehension in this module, and return the largest count any one comprehension reaches. Each
    extra clause is another loop the reader has to unroll in their head while also holding the
    expression and the filters, and past two the expression is usually clearer written as a
    statement.

    A comprehension nested inside another is a separate comprehension with its own clause count,
    which is what keeps a readable nesting of two one-clause comprehensions apart from one
    two-clause flattening.

    Evidence
    --------
    The finding names each comprehension, its collection kind, and its raw loop count. The value is
    the largest loop count in the module.

    Exceptions
    ----------
    A module with no comprehension at all measures zero rather than being skipped. The count is a
    measurement and a project policy owns the ceiling, since a short two-clause flattening or a
    Cartesian product often reads perfectly well and a project wanting one clause says so in its
    policy. How dense the expression and the filters are is a separate question this count does not
    ask.

    Examples
    --------
    `[clean(value) for value in source]` measures `1`. `[cell for row in table for cell in row]`
    measures `2`. `[[cell for cell in row] for row in table]` holds two comprehensions of one
    clause each, so the module measures `1`. A module holding all three measures `2`.

    References
    ----------
    Cites "The Python Tutorial", sections 5.1.3 and 5.1.4 on comprehensions
    Cites "Fluent Python", chapter 2
    """
    relations = subject
    maximum = (
        relations.values("loop_counts")
        .group_by("fact_id", maintain_order=True)
        .agg(pl.col("integer_value").max().cast(pl.UInt64).alias("value"))
    )
    frame = (
        relations.facts()
        .join(maximum, on="fact_id", how="left")
        .with_columns(pl.col("value").fill_null(0))
    )
    return RuleQuery.integer(
        frame,
        pl.col("value"),
        findings=FindingQuery.precise_integer(
            frame,
            pl.col("value"),
            "comprehension loop count",
            evidence=pl.col("evidence"),
        ),
    )
