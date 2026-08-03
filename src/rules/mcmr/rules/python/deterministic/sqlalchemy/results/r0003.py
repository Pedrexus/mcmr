import polars as pl

from ...... import rule
from ......domain.contracts import FixSafety
from ......facts import QueryFact
from ......query import CountQuery, FixQuery, RuleQuery
from ......table import Table
from ..relations import QueryTables, count_query


@rule("PY-SQLA0003", fix_safety=FixSafety.SAFE)
def sqlmodel_execute_scalars_api(subject: Table[QueryFact]) -> CountQuery:
    """Prefer SQLModel `exec` for exact scalar selections.

    Definition
    ----------
    Report `session.execute(select(Item)).scalars()` only when `Session` or `AsyncSession` and
    `select` resolve to SQLModel imports. The direct single-expression form has the same scalar
    result contract as SQLModel `exec` but bypasses SQLModel's typed convenience API.

    Evidence
    --------
    Each finding points to one complete `execute(...).scalars()` chain. The value is the number of
    exact chains.

    Exceptions
    ----------
    Raw SQLAlchemy sessions, multi-expression selects, textual SQL, execution options, statement
    variables, and row-shaped results remain unreported. SQLAlchemy owns those general cases.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       heroes = session.execute(select(Hero)).scalars().all()

    Good
    ~~~~
    .. code-block:: python

       heroes = session.exec(select(Hero)).all()

    References
    ----------
    Cites "SQLModel documentation", selection technical details
    https://sqlmodel.tiangolo.com/tutorial/select/#sqlmodels-sessionexec
    Cites "SQLAlchemy documentation", scalar-result guidance
    https://docs.sqlalchemy.org/en/21/orm/queryguide/select.html#selecting-orm-entities
    """
    relations = QueryTables(subject)
    selected = relations.operations().filter(
        (pl.col("kind") == "execute_scalars")
        & (pl.col("framework") == "sqlmodel")
        & ~pl.col("has_execution_options")
    )
    repairable = selected.filter(
        pl.col("execute_segment.id").is_not_null() & pl.col("scalars_segment.id").is_not_null()
    )
    replace_order = pl.col("ordinal") * 2
    remove_order = replace_order + 1
    replacements = repairable.select(
        "fact_id",
        replace_order.cast(pl.UInt64).alias("rewrite_order"),
        pl.lit("replace").alias("kind"),
        pl.lit("exec").alias("source"),
        pl.lit("").alias("placement"),
        pl.lit("").alias("name"),
        pl.lit("").alias("symbol_id"),
        pl.lit("").alias("symbol_name"),
        pl.lit(False).alias("references_complete"),
    )
    removals = repairable.select(
        "fact_id",
        remove_order.cast(pl.UInt64).alias("rewrite_order"),
        pl.lit("remove").alias("kind"),
        pl.lit("").alias("source"),
        pl.lit("").alias("placement"),
        pl.lit("").alias("name"),
        pl.lit("").alias("symbol_id"),
        pl.lit("").alias("symbol_name"),
        pl.lit(False).alias("references_complete"),
    )
    fix = FixQuery.build(
        "Call the SQLModel `exec` API, which already returns the scalar rows.",
        rewrites=pl.concat([replacements, removals], how="vertical").sort(
            "fact_id", "rewrite_order"
        ),
        nodes=pl.concat(
            [
                relations.rewrite_node(repairable, "execute_segment", replace_order),
                relations.rewrite_node(repairable, "scalars_segment", remove_order),
            ],
            how="vertical",
        ).sort("fact_id", "rewrite_order"),
    )
    query = count_query(
        relations,
        selected,
        message="SQLModel `execute(...).scalars()` bypasses the typed `exec` API",
        measurement="sqlmodel execute scalars api",
    )
    return RuleQuery[int](values=query.values, findings=query.findings, fix=fix)
