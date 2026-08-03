import polars as pl

from ...... import rule
from ......domain.contracts import FixSafety
from ......facts import QueryFact
from ......query import CountQuery, FixQuery, RuleQuery
from ......table import Table
from ..relations import QueryTables, count_query


@rule("PY-SQLA0004", fix_safety=FixSafety.SAFE)
def sqlmodel_redundant_scalars(subject: Table[QueryFact]) -> CountQuery:
    """Remove scalar extraction repeated after SQLModel `exec`.

    Definition
    ----------
    Report `session.exec(select(Item)).scalars()` only when the session and `select` resolve to
    SQLModel and the select contains exactly one expression. SQLModel already applies scalar
    extraction for that statement shape.

    Evidence
    --------
    Each finding points to one redundant `scalars` call. The value is the number of exact chains.

    Exceptions
    ----------
    Multi-expression selects and unresolved sessions remain unreported because SQLModel preserves
    row-shaped results for those statements.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       heroes = session.exec(select(Hero)).scalars().all()

    Good
    ~~~~
    .. code-block:: python

       heroes = session.exec(select(Hero)).all()

    References
    ----------
    Cites "SQLModel documentation", selection technical details
    https://sqlmodel.tiangolo.com/tutorial/select/#sqlmodels-sessionexec
    Cites "SQLModel documentation", compact selection example
    https://sqlmodel.tiangolo.com/tutorial/select/#compact-version
    """
    relations = QueryTables(subject)
    selected = relations.operations().filter(
        (pl.col("kind") == "exec_scalars")
        & (pl.col("framework") == "sqlmodel")
        & (pl.col("selected_expression_count") == 1)
    )
    repairable = selected.filter(pl.col("scalars_segment.id").is_not_null())
    rewrites = repairable.select(
        "fact_id",
        pl.col("ordinal").cast(pl.UInt64).alias("rewrite_order"),
        pl.lit("remove").alias("kind"),
        pl.lit("").alias("source"),
        pl.lit("").alias("placement"),
        pl.lit("").alias("name"),
        pl.lit("").alias("symbol_id"),
        pl.lit("").alias("symbol_name"),
        pl.lit(False).alias("references_complete"),
    )
    fix = FixQuery.build(
        "Drop the `scalars` segment that SQLModel `exec` already applied.",
        rewrites=rewrites,
        nodes=relations.rewrite_node(repairable, "scalars_segment", pl.col("ordinal")),
    )
    query = count_query(
        relations,
        selected,
        message="`scalars()` repeats scalar extraction already performed by SQLModel `exec`",
        measurement="sqlmodel redundant scalars",
    )
    return RuleQuery[int](values=query.values, findings=query.findings, fix=fix)
