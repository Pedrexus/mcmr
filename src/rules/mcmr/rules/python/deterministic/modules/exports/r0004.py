import polars as pl

from ...... import rule
from ......domain.contracts import FixSafety
from ......facts import ModuleFact
from ......query import FixQuery, OccurrenceQuery
from ......table import Table
from .....general.deterministic.modules import occurrence_query


@rule("PY-MODU0004", fix_safety=FixSafety.REVIEW)
def explicit_all_only_in_initializer(subject: Table[ModuleFact]) -> OccurrenceQuery:
    """Keep explicit package export lists inside package initializers.

    Definition
    ----------
    Report an ordinary Python module that assigns or extends `__all__`. A defining module already
    publishes its public names through ordinary Python visibility, while a package initializer is
    the one place that combines sibling definitions into a package surface.

    Evidence
    --------
    Each finding covers the complete module that declares `__all__`. The Boolean value is true
    only when that declaration appears outside `__init__.py`.

    Exceptions
    ----------
    Package initializers may build `__all__` through assignments, annotations, or augmented
    assignments. A generated compatibility facade can exclude its exact path while the migration
    that requires it remains active.

    Examples
    --------
    Bad
    ~~~
    `service.py` containing `__all__ = [\"Client\"]` returns `true`.

    Good
    ~~~~
    The same declaration in `service/__init__.py` returns `false`.

    References
    ----------
    Cites "The Python Language Reference", the import statement
    https://docs.python.org/3.14/reference/simple_stmts.html#the-import-statement
    Cites "PEP 8, Style Guide for Python Code", Public and Internal Interfaces
    https://peps.python.org/pep-0008/#public-and-internal-interfaces
    """
    frame = subject.facts().with_columns(
        (pl.col("declares_all") & ~pl.col("is_package_initializer")).alias("value")
    )
    nodes = (
        subject.records("all_declarations")
        .join(frame.filter(pl.col("value")).select("fact_id"), on="fact_id", how="semi")
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
    query = occurrence_query(frame, "explicit all outside initializer")
    return query.model_copy(
        update={
            "fix": FixQuery.build(
                "Remove the ordinary module's explicit export declarations.",
                rewrites=rewrites,
                nodes=targets,
            )
        }
    )
