import polars as pl

from ..... import Numeric, rule
from .....facts import TryBlockFact
from .....query import CountQuery, FindingQuery, RuleQuery
from .....table import Table


@rule("PY-EXCE0002", policy=Numeric(maximum=1))
def bounded_exception_region(
    subject: Table[TryBlockFact],
) -> CountQuery:
    """Keep each try, except, else, and finally clause narrowly scoped.

    Definition
    ----------
    Count the executable statements inside every `try`, `except`, `else`, and `finally` clause,
    including the statements nested below a compound `if`, loop, context manager, or match case,
    and return the largest count any one clause reaches. A nested function, a nested class, and a
    nested `try` each open their own scope and are counted there instead.

    A wide protected region is what makes an exception handler ambiguous. Four statements under one
    `try` means four things could have raised, so the handler below it is answering for a failure
    nobody can name, and the recovery it performs is right for at most one of them.

    Evidence
    --------
    The finding names the clause, its line, and its statement count. The value is the largest
    clause statement count in this file. How specific the caught type is stays a separate question,
    owned by Ruff `BLE001` and Pylint `W0718`.

    Exceptions
    ----------
    A file with no exception clause at all measures zero. The count is a measurement and a project
    policy owns the ceiling, so a resource protocol that has to acquire and use in one protected
    region raises it rather than fighting it. The repository's Git ignore files or a per-rule glob
    can exclude generated or vendored sources. Widening the ceiling is only right when moving a
    statement out would change the protected transaction or the cleanup guarantee.

    Examples
    --------
    A `try` clause holding only `payload = path.read_text()` beneath an `except OSError` measures
    `1`, and the failure boundary is unambiguous. A `try` clause that reads a file, parses it,
    transforms the model, and updates shared state measures `4`, and its handler now answers for
    four different failures. A handler clause holding a log call and a re-raise measures `2`.

    References
    ----------
    Cites "The Python Tutorial", handling exceptions
    https://docs.python.org/3/tutorial/errors.html#handling-exceptions
    Cites "The Python Language Reference", the try statement
    https://docs.python.org/3/reference/compound_stmts.html#the-try-statement
    Cites Ruff TRY300 try-consider-else
    https://docs.astral.sh/ruff/rules/try-consider-else/
    Cites Ruff BLE001 blind-except
    https://docs.astral.sh/ruff/rules/blind-except/
    """
    relations = subject
    maximum = (
        relations.values("regions.clause_statement_counts")
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
            "bounded exception region",
            evidence=pl.col("evidence"),
        ),
    )
