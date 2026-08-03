import polars as pl

from ...... import rule
from ......domain.contracts import FixSafety
from ......facts import ImportBindingFact, ProjectConfigurationFact
from ......query import FindingQuery, FixQuery, RuleQuery
from ......table import ImportBindingRelation, Table


@rule("PY-TYPE0001", fix_safety=FixSafety.REVIEW)
def future_annotations_import(
    subject: Table[ImportBindingFact],
    *,
    configuration: Table[ProjectConfigurationFact],
) -> RuleQuery[bool]:
    """Detect PEP 563 annotation stringization in Python 3.14 projects.

    Definition
    ----------
    Report `from __future__ import annotations` when the configured minimum Python 3 minor
    version is 14 or newer. Python 3.14 provides deferred annotation evaluation through PEP
    649 and PEP 749 without the import. Keeping it instead selects the older PEP 563 stringized
    representation. A plain one-line import receives a review fix that removes the full line.

    Evidence
    --------
    Each finding identifies the future import and includes a source-preserving byte edit when
    removal does not share a line or statement with other code.

    Exceptions
    ----------
    Keep the import when software intentionally depends on PEP 563 stringized runtime annotations.
    The import remains supported in Python 3.14 and is planned for deprecation only after Python
    3.13 reaches end of life. The fix requires review because removal changes runtime annotation
    representation even though ordinary static annotations remain valid. The project configuration
    table supplies the minimum supported Python minor, so a project still supporting an older
    interpreter stops asking for syntax that release does not have.

    Examples
    --------
    A module targeting Python 3.14 that states `from __future__ import annotations` returns `true`
    and can drop that line. The same module without the import returns `false`, and so does any
    module in a project whose declared minimum is below 14.

    References
    ----------
    Adapts Pylint W0410 misplaced-future
    Cites "What's New In Python", `from __future__ import annotations`
    https://docs.python.org/3.14/whatsnew/3.14.html#pep-649-and-pep-749-deferred-evaluation-of-annotations
    Cites "PEP 649, Deferred Evaluation of Annotations"
    https://peps.python.org/pep-0649/
    Cites "PEP 749, Implementing PEP 649", the future of PEP 563
    https://peps.python.org/pep-0749/#the-future-of-from-future-import-annotations
    """
    target = configuration.facts().select(
        pl.col("python_target.project_minimum_minor").min().fill_null(14).alias("python_minor")
    )
    frame = subject.lazy(ImportBindingRelation.FACTS).join(target, how="cross")
    imported = (
        pl.when(pl.col("imported_name") != "")
        .then(pl.col("imported_name"))
        .otherwise(pl.col("name"))
    )
    value = (
        (pl.col("python_minor") >= 14)
        & (pl.col("module") == "__future__")
        & (imported == "annotations")
    )
    selected = frame.filter(value & (pl.col("declaration_id") != "")).select("fact_id")
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
        .filter(pl.col("role") == "declaration")
        .join(selected, on="fact_id", how="inner")
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
        "Remove an annotations import the target Python version no longer needs.",
        rewrites=rewrites,
        nodes=nodes,
    )
    return RuleQuery.boolean(
        frame,
        value,
        findings=FindingQuery.precise_boolean(frame, value, "future annotations import"),
        fix=fix,
    )
