import polars as pl

from ...... import rule
from ......domain.contracts import (
    FixSafety,
    Unit,
)
from ......facts import ImportBindingFact
from ......query import FindingQuery, FixQuery, OccurrenceQuery, RuleQuery
from ......table import ImportBindingRelation, Table


@rule("PY-IMPO0003", fix_safety=FixSafety.REVIEW)
def unused_import(subject: Table[ImportBindingFact]) -> OccurrenceQuery:
    """Report an unused import binding.

    Definition
    ----------
    Report one resolved import binding that nothing in its own module reads. A read is counted
    wherever the interpreter would perform one, so a name tested by an `elif`, named as the type
    an `except` catches, matched by a `case`, deleted, used as a decorator, or spelled inside a
    string in a type expression is read exactly as much as a name a call passes. That is the
    complete boundary.

    Three statements are never judged. A `__future__` import is a compiler directive that binds
    nothing a reader was ever meant to use. A wildcard import binds names this reader cannot
    enumerate, so its disuse is unprovable rather than proven. An import written inside a `try`
    that states what to do when an import fails is there for whether it succeeds.

    Evidence
    --------
    The finding names the binding, the module it came from, and the exact line that states it,
    beside how many references resolved to it, which is the zero the rule turned on. The removal
    arrives from the fix this rule already declares rather than from a second statement of the
    same edit.

    Exceptions
    ----------
    Keep imports that form an explicit public re-export, register behavior with a framework, or
    intentionally execute a documented module side effect. A name a module lists in `__all__` is
    re-exported however that list is built, and so is a name an import restates as its own alias.

    A string inside a subscript is read as the name it spells, since that is where a forward
    reference lives, so a mapping key matching an import silences this rule for that import.
    Reading it the other way would report a live forward reference and offer to delete it, which
    is the failure worth avoiding.

    Examples
    --------
    Bad
    ~~~
    .. code-block:: python

       import json

    Good
    ~~~~
    .. code-block:: python

       from __future__ import annotations
       from .api import Client as Client
       from .transports import *

       try:
           import h2
       except ImportError:
           raise ImportError("install the http2 extra") from None

    References
    ----------
    Generalizes Pylint W0611 unused-import
    Generalizes Ruff F401 unused-import
    Cites "Pyflakes", unused import analysis
    Cites "The Python Language Reference", the import system
    """
    frame = subject.lazy(ImportBindingRelation.FACTS)
    exempt = (
        pl.col("has_qualifying_use")
        | pl.col("is_reexported")
        | pl.col("has_documented_side_effect")
        | pl.col("is_wildcard")
        | (pl.col("module") == "__future__")
    )
    value = ~exempt & (pl.col("reference_count") == 0)
    evidence = (
        subject.lazy(ImportBindingRelation.EVIDENCE)
        .group_by("fact_id", maintain_order=True)
        .agg(pl.col("signal").sort_by("ordinal").alias("evidence"))
    )
    declaration = (
        subject.lazy(ImportBindingRelation.NODES)
        .filter(pl.col("role") == "declaration")
        .select(
            "fact_id",
            pl.col("path").alias("finding_path"),
            pl.col("start_line").alias("finding_start_line"),
            pl.col("start_column").alias("finding_start_column"),
            pl.col("end_line").alias("finding_end_line"),
            pl.col("end_column").alias("finding_end_column"),
        )
    )
    finding_rows = (
        frame.filter(value)
        .join(declaration, on="fact_id", how="left")
        .join(evidence, on="fact_id", how="left")
        .with_columns(
            pl.coalesce("finding_path", "path").alias("path"),
            pl.coalesce("finding_start_line", "start_line").alias("start_line"),
            pl.coalesce("finding_start_column", "start_column").alias("start_column"),
            pl.coalesce("finding_end_line", "end_line").alias("end_line"),
            pl.coalesce("finding_end_column", "end_column").alias("end_column"),
            pl.col("evidence").fill_null(pl.lit([], dtype=pl.List(pl.String))),
        )
    )
    findings = FindingQuery.build(
        finding_rows,
        pl.concat_str(
            pl.lit("`"),
            pl.col("name"),
            pl.lit("` is imported from `"),
            pl.col("module"),
            pl.lit("` and nothing in this file reads it"),
        ),
        (("references to it", pl.col("reference_count"), Unit.COUNT),),
        evidence=pl.col("evidence"),
    )
    selected = frame.filter(
        value
        & (pl.col("declaration_id") != "")
        & (pl.col("is_sole_binding") | (pl.col("binding_id") != ""))
    ).select(
        "fact_id",
        pl.when(pl.col("is_sole_binding"))
        .then(pl.lit("declaration"))
        .otherwise(pl.lit("binding"))
        .alias("target_role"),
    )
    rewrites = selected.select(
        "fact_id",
        pl.lit(0, dtype=pl.UInt64).alias("rewrite_order"),
        pl.lit("remove").alias("kind"),
        pl.lit("").alias("source"),
        pl.lit("").alias("placement"),
        pl.lit("").alias("name"),
        pl.lit("").alias("symbol_id"),
        pl.lit("").alias("symbol_name"),
        pl.lit(False).alias("references_complete"),
    )
    nodes = (
        subject.lazy(ImportBindingRelation.NODES)
        .join(selected, on="fact_id", how="inner")
        .filter(pl.col("role") == pl.col("target_role"))
        .select(
            "fact_id",
            pl.lit(0, dtype=pl.UInt64).alias("rewrite_order"),
            pl.lit("target").alias("role"),
            pl.lit(0, dtype=pl.UInt64).alias("ordinal"),
            pl.col("node_id").alias("id"),
            "path",
            "start_line",
            "start_column",
            "end_line",
            "end_column",
            "kind",
            "text",
        )
    )
    fix = FixQuery.build(
        "Delete the exact import binding that nothing reads.",
        rewrites=rewrites,
        nodes=nodes,
    )
    return RuleQuery.boolean(frame, value, findings=findings, fix=fix)
