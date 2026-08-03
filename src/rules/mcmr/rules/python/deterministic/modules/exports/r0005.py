import polars as pl

from ...... import rule
from ......domain.contracts import FixSafety, Unit
from ......facts import ExportFact
from ......query import CountQuery, FindingQuery, FixQuery, RuleQuery
from ......table import Table


@rule("PY-MODU0005", fix_safety=FixSafety.REVIEW)
def unused_explicit_export(subject: Table[ExportFact]) -> CountQuery:
    """Count explicit package exports no repository consumer uses.

    Definition
    ----------
    Read every name a Python module explicitly publishes through `__all__` and count references
    that enter through that public module and name. Report an export when no other source file uses
    the route. Direct use of the defining module does not prove the extra public route useful.

    Evidence
    --------
    Each finding names the public name, the declaration it resolves to, and the exporting module.
    The value is the number of explicit exports with zero repository consumers.

    Exceptions
    ----------
    A library may intentionally publish an API only external clients use. Exclude that exact public
    boundary when the release contract proves the consumer exists outside the scanned repository.
    Dynamic string lookup is not counted because it does not state the import route statically.

    Examples
    --------
    Bad
    ~~~
    `pkg.__all__` lists `Engine`, but no repository file imports or accesses `pkg.Engine`.

    Good
    ~~~~
    `from pkg import Client` consumes the explicit `Client` export and returns zero for that name.

    References
    ----------
    Cites "The Python Language Reference", the import statement and `__all__`
    Cites "Refactoring", Remove Dead Code
    """
    relations = subject
    selected = (
        relations.facts()
        .filter(pl.col("public_export.consumer_count") == 0)
        .with_columns(
            pl.col("public_export.name").alias("name"),
            pl.col("public_export.target").alias("target"),
        )
    )
    nodes = (
        relations.records("public_export.nodes")
        .join(selected.select("fact_id"), on="fact_id", how="semi")
        .with_columns(pl.col("ordinal").cast(pl.UInt64).alias("rewrite_order"))
    )
    rewrites = nodes.select(
        "fact_id",
        "rewrite_order",
        pl.lit("remove").alias("kind"),
        pl.lit("").alias("source"),
        pl.lit("").alias("placement"),
        pl.lit("").alias("name"),
        pl.lit("").alias("symbol_id"),
        pl.lit("").alias("symbol_name"),
        pl.lit(False).alias("references_complete"),
    )
    targets = nodes.select(
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
    )
    frame = relations.counted(selected)
    return RuleQuery.integer(
        frame,
        pl.col("value"),
        findings=FindingQuery.build(
            selected,
            pl.concat_str(
                pl.lit("`"),
                pl.col("name"),
                pl.lit("` explicitly exports `"),
                pl.col("target"),
                pl.lit("`, but no repository consumer uses that public route"),
            ),
            (("unused explicit export", pl.lit(1), Unit.COUNT),),
        ),
        fix=FixQuery.build(
            "Remove the unused name from the explicit package export list.",
            rewrites=rewrites,
            nodes=targets,
        ),
    )
