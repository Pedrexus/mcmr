import polars as pl
from pydantic import NonNegativeInt

from ...... import rule
from ......domain.contracts import FixSafety
from ......facts import FunctionFact
from ......query import FindingQuery, FixQuery, RuleQuery
from ......table import FunctionRelation, Table


@rule("ALL-FUNC0002", fix_safety=FixSafety.REVIEW)
def single_use_trivial_helper(
    subject: Table[FunctionFact],
    *,
    maximum_lines: NonNegativeInt = 1,
    ignore_names: tuple[str, ...] = (),
) -> RuleQuery[bool]:
    """Detect a private one-line helper with only one local reference.

    Definition
    ----------
    Inspect undecorated private functions declared directly at module scope. After omitting an
    optional docstring, require exactly one non-`pass`, non-`raise` statement, no more than
    `maximum_lines` executable lines, and exactly one loaded reference outside the function body
    in the same module. The Boolean result reports whether this function is a candidate.

    Evidence
    --------
    Each finding identifies the helper definition and its only local reference. The rule does not
    edit code because inlining can change evaluation order, exception location, or debugging.

    Exceptions
    ----------
    Public functions, methods, nested functions, decorated hooks, callbacks, fixtures, overloads,
    protocol implementations, recursive helpers, unused functions, and helpers with multiple
    references are excluded structurally. `ignore_names` retains a deliberate named boundary.
    Vulture remains responsible for functions with no uses.

    Examples
    --------
    Bad
    ~~~
    `_normalize = lambda` is not required. An undecorated `_normalize` whose body is only
    `return value.strip()` and which is called once is reported for possible inlining.

    Good
    ~~~~
    The same helper called from three sites remains. A decorated one-line route handler, a public
    adapter, and a multiline expression with one top-level `return` are not candidates.

    References
    ----------
    Cites "A Philosophy of Software Design", chapter 4, shallow modules
    Cites "Clean Code", chapter 3, small functions
    Cites "Vulture documentation", unused code boundary
    https://github.com/jendrikseipp/vulture
    """
    decorator_counts = (
        subject.lazy(FunctionRelation.DECORATORS)
        .group_by("function_id")
        .agg(pl.len().cast(pl.UInt64).alias("decorator_count"))
    )
    frame = (
        subject.lazy(FunctionRelation.FUNCTIONS)
        .join(
            decorator_counts,
            left_on="entity_id",
            right_on="function_id",
            how="left",
        )
        .with_columns(pl.col("decorator_count").fill_null(0))
    )
    value = (
        (pl.col("scope") == "module")
        & (pl.col("visibility") != "public")
        & (pl.col("decorator_count") == 0)
        & (pl.col("direct_statement_count") == 1)
        & (pl.col("implementation_lines") <= maximum_lines)
        & (pl.col("reference_count") == 1)
        & ~pl.col("is_recursive")
        & ~pl.col("is_first_class_reference")
        & ~pl.col("is_pass_body")
        & ~pl.col("is_raise_body")
        & ~pl.col("name").is_in(list(ignore_names))
    )
    references = subject.lazy(FunctionRelation.REFERENCES)
    repairable = frame.filter(
        pl.col("definition_id").is_not_null() & pl.col("body_expression_id").is_not_null()
    ).join(
        references.select("function_id").unique(),
        left_on="entity_id",
        right_on="function_id",
        how="inner",
    )
    rewrites = repairable.select(
        "fact_id",
        pl.lit(0, dtype=pl.UInt64).alias("rewrite_order"),
        pl.lit("inline").alias("kind"),
        pl.lit("").alias("source"),
        pl.lit("").alias("placement"),
        pl.lit("").alias("name"),
        pl.lit("").alias("symbol_id"),
        pl.lit("").alias("symbol_name"),
        pl.lit(False).alias("references_complete"),
    )
    definition_nodes = repairable.select(
        "fact_id",
        pl.lit(0, dtype=pl.UInt64).alias("rewrite_order"),
        pl.lit("declaration").alias("role"),
        pl.lit(0, dtype=pl.UInt64).alias("ordinal"),
        pl.col("definition_id").alias("id"),
        pl.col("definition_path").alias("path"),
        pl.col("definition_start_line").alias("start_line"),
        pl.col("definition_start_column").alias("start_column"),
        pl.col("definition_end_line").alias("end_line"),
        pl.col("definition_end_column").alias("end_column"),
        pl.col("definition_kind").alias("kind"),
        pl.col("definition_text").alias("text"),
    )
    body_nodes = repairable.select(
        "fact_id",
        pl.lit(0, dtype=pl.UInt64).alias("rewrite_order"),
        pl.lit("body").alias("role"),
        pl.lit(0, dtype=pl.UInt64).alias("ordinal"),
        pl.col("body_expression_id").alias("id"),
        pl.col("body_expression_path").alias("path"),
        pl.col("body_expression_start_line").alias("start_line"),
        pl.col("body_expression_start_column").alias("start_column"),
        pl.col("body_expression_end_line").alias("end_line"),
        pl.col("body_expression_end_column").alias("end_column"),
        pl.col("body_expression_kind").alias("kind"),
        pl.col("body_expression_text").alias("text"),
    )
    reference_nodes = references.join(
        repairable.select("entity_id", "fact_id"),
        left_on="function_id",
        right_on="entity_id",
        how="inner",
    ).select(
        "fact_id",
        pl.lit(0, dtype=pl.UInt64).alias("rewrite_order"),
        pl.lit("reference").alias("role"),
        "ordinal",
        pl.col("node_id").alias("id"),
        "path",
        "start_line",
        "start_column",
        "end_line",
        "end_column",
        "kind",
        "text",
    )
    fix = FixQuery.build(
        "Replace the single reference with the helper body, then delete the declaration.",
        rewrites=rewrites,
        nodes=pl.concat(
            [definition_nodes, body_nodes, reference_nodes],
            how="vertical",
        ).sort("fact_id", "rewrite_order", "role", "ordinal"),
    )
    return RuleQuery.boolean(
        frame,
        value,
        findings=FindingQuery.precise_boolean(frame, value, "single use trivial helper"),
        fix=fix,
    )
