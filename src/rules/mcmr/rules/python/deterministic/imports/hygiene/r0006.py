import polars as pl

from ...... import rule
from ......domain.contracts import FixSafety, Unit
from ......facts import ExportFact
from ......query import CountQuery, FindingQuery, FixQuery, RuleQuery
from ......table import Table


def public_import_candidates(subject: Table[ExportFact]) -> pl.LazyFrame:
    """Return complete cycle-safe statements that can use one explicit public facade."""
    selected = subject.records("bypasses")
    candidates = selected.filter(
        pl.col("is_cycle_safe")
        & pl.col("module_node.id").is_not_null()
        & pl.col("replacement_module").is_not_null()
    )
    complete = (
        candidates.group_by("module_node.id", "replacement_module", maintain_order=True)
        .agg(
            pl.len().alias("candidate_count"),
            pl.col("binding_count").first(),
            pl.col("binding_count").n_unique().alias("binding_count_variants"),
        )
        .filter(
            (pl.col("candidate_count") == pl.col("binding_count"))
            & (pl.col("binding_count_variants") == 1)
        )
        .select("module_node.id", "replacement_module")
    )
    return candidates.join(
        complete,
        on=["module_node.id", "replacement_module"],
        how="semi",
    ).unique(subset=["module_node.id"], maintain_order=True)


def public_import_fix(candidates: pl.LazyFrame, summary: str) -> FixQuery:
    """Build exact module-node replacements from already proven facade candidates."""
    rewrites = candidates.select(
        "fact_id",
        pl.col("ordinal").cast(pl.UInt64).alias("rewrite_order"),
        pl.lit("replace").alias("kind"),
        pl.col("replacement_module").alias("source"),
        pl.lit("").alias("placement"),
        pl.lit("").alias("name"),
        pl.lit("").alias("symbol_id"),
        pl.lit("").alias("symbol_name"),
        pl.lit(False).alias("references_complete"),
    )
    nodes = candidates.select(
        "fact_id",
        pl.col("ordinal").cast(pl.UInt64).alias("rewrite_order"),
        pl.lit("target").alias("role"),
        pl.lit(0, dtype=pl.UInt64).alias("ordinal"),
        pl.col("module_node.id").alias("id"),
        pl.col("module_node.span.path").alias("path"),
        pl.col("module_node.span.start_line").cast(pl.UInt64).alias("start_line"),
        pl.col("module_node.span.start_column").cast(pl.UInt64).alias("start_column"),
        pl.col("module_node.span.end_line").cast(pl.UInt64).alias("end_line"),
        pl.col("module_node.span.end_column").cast(pl.UInt64).alias("end_column"),
        pl.col("module_node.kind").alias("kind"),
        pl.col("module_node.text").alias("text"),
    )
    return FixQuery.build(
        summary,
        rewrites=rewrites,
        nodes=nodes,
    )


@rule("PY-IMPO0006", fix_safety=FixSafety.SAFE)
def bypassed_public_import(subject: Table[ExportFact]) -> CountQuery:
    """Count imports that bypass the shortest explicit project package surface.

    Definition
    ----------
    Resolve every explicit `__all__` export to its defining declaration. When several packages
    export the same declaration, keep the shortest public route. Report a direct import of the
    defining module when that shorter route already exists.

    Evidence
    --------
    Each finding names the import expression, the preferred package and name, and the exact import
    line. The value is the number of imports bypassing a shorter explicit public route.

    Exceptions
    ----------
    Imports within the exporting initializer are excluded because they construct the public route.
    Imports from modules inside either the exporting package or the defining package are excluded
    because they are implementation details and routing them through a facade can create import
    cycles. A declaration with no explicit package export has no route to prefer. External packages
    are not inspected, since their installed public surface is outside the repository graph. The
    fix changes the module path only when every binding in the statement reaches the same facade,
    its existing relative dots can reach that facade, and the facade cannot reach the importing
    module through the import graph. Every other bypass remains a finding for review.

    Examples
    --------
    Bad
    ~~~
    `from mcmr.project.configuration import ScanConfiguration` bypasses an explicit
    `mcmr.ScanConfiguration` export.

    Good
    ~~~~
    `from mcmr import ScanConfiguration` uses the shortest explicit surface.

    References
    ----------
    Cites "PEP 8, Style Guide for Python Code", Public and Internal Interfaces
    Cites "The Python Language Reference", packages and the import statement
    """
    relations = subject
    selected = relations.records("bypasses").with_columns(
        pl.col("span.path").alias("path"),
        pl.col("span.start_line").cast(pl.UInt64).alias("start_line"),
        pl.col("span.start_column").cast(pl.UInt64).alias("start_column"),
        pl.col("span.end_line").cast(pl.UInt64).alias("end_line"),
        pl.col("span.end_column").cast(pl.UInt64).alias("end_column"),
    )
    frame = relations.counted(selected)
    return RuleQuery.integer(
        frame,
        pl.col("value"),
        findings=FindingQuery.build(
            selected,
            pl.concat_str(
                pl.lit("`"),
                pl.col("expression"),
                pl.lit("` bypasses the shorter public import `"),
                pl.col("public_module"),
                pl.lit("."),
                pl.col("name"),
                pl.lit("`"),
            ),
            (("bypassed public import", pl.lit(1), Unit.COUNT),),
            finding_order=pl.col("ordinal"),
        ),
        fix=public_import_fix(
            public_import_candidates(subject),
            "Replace a defining-module import with its shortest explicit public route.",
        ),
    )
