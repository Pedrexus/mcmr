import polars as pl

from ...... import Numeric, rule
from ......domain.contracts import FixSafety
from ......facts import ExportFact, ImportBindingFact
from ......query import CountQuery, FindingQuery, RuleQuery
from ......table import ImportBindingRelation, Table
from .r0006 import public_import_candidates, public_import_fix


@rule("PY-IMPO0005", policy=Numeric(maximum=3), fix_safety=FixSafety.SAFE)
def import_module_depth(
    subject: Table[ImportBindingFact],
    exports: Table[ExportFact],
) -> CountQuery:
    """Measure the named module depth of one import statement.

    Definition
    ----------
    Count the dot-separated names in the module an import states. Leading relative dots do not
    name modules and therefore add nothing. Every statement is measured once even when it imports
    several bindings, since the module path is shared by the whole statement.

    Evidence
    --------
    Each finding names the import statement and its named module depth. The returned value is that
    depth. A project policy owns the ceiling, which defaults to three components.

    Exceptions
    ----------
    A bare relative import such as `from .. import value` has no named component and returns zero.
    Relative level is checked separately by `PY-IMPO0004` because climbing and naming are different
    properties.

    Examples
    --------
    Bad
    ~~~
    `from library.internal.transport.http import Client` returns `4`.

    Good
    ~~~~
    `from ...transport.http import Client` returns `2`, ignoring the leading relative dots.

    References
    ----------
    Cites "The Python Language Reference", the import statement
    Cites "A Philosophy of Software Design", information hiding and navigation cost
    """
    bindings = subject.lazy(ImportBindingRelation.FACTS).with_columns(
        pl.when(pl.col("declaration_id") != "")
        .then(pl.col("declaration_id"))
        .otherwise(pl.col("fact_id"))
        .alias("statement_id")
    )
    statements = bindings.group_by("statement_id", maintain_order=True).agg(pl.all().first())
    named = pl.col("module").str.strip_chars_start(".")
    depth = pl.when(named == "").then(0).otherwise(named.str.split(".").list.len()).cast(pl.UInt64)
    facades = public_import_candidates(exports).select(
        pl.col("module_node.id").alias("facade_module_node_id"),
        "replacement_module",
        pl.col("module_node.id").alias("module_node.id"),
        pl.col("module_node.span.path").alias("module_node.span.path"),
        pl.col("module_node.span.start_line").alias("module_node.span.start_line"),
        pl.col("module_node.span.start_column").alias("module_node.span.start_column"),
        pl.col("module_node.span.end_line").alias("module_node.span.end_line"),
        pl.col("module_node.span.end_column").alias("module_node.span.end_column"),
        pl.col("module_node.kind").alias("module_node.kind"),
        pl.col("module_node.text").alias("module_node.text"),
    )
    repairable = (
        statements.filter(depth > 3)
        .join(
            facades,
            left_on="module_node_id",
            right_on="facade_module_node_id",
            how="inner",
        )
        .filter(pl.col("replacement_module").str.split(".").list.len() <= 3)
        .with_columns(pl.lit(0, dtype=pl.UInt64).alias("ordinal"))
    )
    return RuleQuery.integer(
        statements,
        depth,
        findings=FindingQuery.precise_integer(statements, depth, "named import depth"),
        fix=public_import_fix(
            repairable,
            "Replace a deep defining-module import with its proven public facade.",
        ),
    )
