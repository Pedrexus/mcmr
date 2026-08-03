import polars as pl

from ..... import rule
from .....domain.contracts import FixSafety
from .....facts import ComprehensionFact
from .....query import CountQuery, FindingQuery, FixQuery, RuleQuery
from .....table import Table


@rule("PY-COMP0002", fix_safety=FixSafety.SAFE)
def manual_set_comprehension(subject: Table[ComprehensionFact]) -> CountQuery:
    """Count fresh sets populated by a loop that can be one set comprehension.

    Definition
    ----------
    Detect a local name initialized by the unshadowed builtin `set()` immediately before a
    synchronous `for` loop. Require the loop's only effect to be `name.add(expression)`, optionally
    inside one `if` without an `else`. Convert that condition directly into the comprehension
    filter. The result is the number of proven candidates. A safe UTF-8 edit replaces the
    initialization and loop when every required expression is available as single-line source.

    Evidence
    --------
    Each finding identifies the fresh set, initialization-to-loop range, and loop line. The safe
    fix preserves a plain or annotated assignment and retains the iterable, target, expression, and
    optional condition in their original evaluation order. The value is the number of loops a set
    comprehension would replace exactly.

    Exceptions
    ----------
    Abstain when `set` is shadowed, the loop is asynchronous, the set already contains values, the
    body has multiple effects, an `else` or control-flow statement exists, or the expression reads
    the set being built. Also abstain inside exception handlers, in module or class scope, when a
    a loop binding is referenced elsewhere in its function, or when assignment expressions,
    `await`, or `yield` make scope and evaluation semantics differ. Attribute-only targets and
    dynamic local-scope introspection also suppress the finding. Comments suppress the automatic
    edit rather than being deleted.

    Examples
    --------
    Bad
    ~~~
    `values = set(); for item in source: values.add(normalize(item))` manually builds a set.
    A body containing only `if item.valid: values.add(item.key)` is the filtered form.

    Good
    ~~~~
    `values = {normalize(item) for item in source}` and
    `values = {item.key for item in source if item.valid}` state the collection directly. A loop
    with logging, an `else`, an async iterator, or later use of `item` remains explicit.

    References
    ----------
    Cites "The Python Tutorial", Sets and set comprehensions
    https://docs.python.org/3.14/tutorial/datastructures.html#sets
    Cites "The Python Language Reference", Displays for lists, sets and dictionaries
    https://docs.python.org/3.14/reference/expressions.html#displays-for-lists-sets-and-dictionaries
    Cites "Fluent Python", chapter 2, An Array of Sequences
    """
    relations = subject
    candidates = relations.records("set_loop_candidates")
    convertible = (
        pl.col("has_unshadowed_set_initialization")
        & pl.col("loop_is_synchronous")
        & pl.col("only_effect_is_add")
        & (pl.col("conditional_count") <= 1)
        & ~pl.col("has_else")
    )
    selected = candidates.filter(convertible)
    frame = relations.counted(selected)
    conditions = (
        relations.records("set_loop_candidates.conditions")
        .group_by("parent_id", maintain_order=True)
        .agg(
            pl.concat_str(pl.lit(" if "), pl.col("text"))
            .sort_by("ordinal")
            .alias("condition_clauses")
        )
    )
    fixable = (
        candidates.filter(
            convertible
            & (pl.col("name") != "")
            & pl.col("initialization.id").is_not_null()
            & pl.col("loop.id").is_not_null()
            & pl.col("element.id").is_not_null()
            & pl.col("target.id").is_not_null()
            & pl.col("iterable.id").is_not_null()
        )
        .join(conditions, left_on="record_id", right_on="parent_id", how="left")
        .with_columns(pl.col("condition_clauses").fill_null(pl.lit([], dtype=pl.List(pl.String))))
        .with_columns(
            pl.concat_str(
                pl.col("name"),
                pl.lit(" = {"),
                pl.col("element.text"),
                pl.lit(" for "),
                pl.col("target.text"),
                pl.lit(" in "),
                pl.col("iterable.text"),
                pl.col("condition_clauses").list.join(""),
                pl.lit("}"),
            ).alias("replacement")
        )
    )
    replacement_order = pl.col("ordinal").cast(pl.UInt64) * 2
    removal_order = replacement_order + 1
    rewrites = pl.concat(
        [
            fixable.select(
                "fact_id",
                replacement_order.alias("rewrite_order"),
                pl.lit("replace").alias("kind"),
                pl.col("replacement").alias("source"),
                pl.lit("").alias("placement"),
                pl.lit("").alias("name"),
                pl.lit("").alias("symbol_id"),
                pl.lit("").alias("symbol_name"),
                pl.lit(False).alias("references_complete"),
            ),
            fixable.select(
                "fact_id",
                removal_order.alias("rewrite_order"),
                pl.lit("remove").alias("kind"),
                pl.lit("").alias("source"),
                pl.lit("").alias("placement"),
                pl.lit("").alias("name"),
                pl.lit("").alias("symbol_id"),
                pl.lit("").alias("symbol_name"),
                pl.lit(False).alias("references_complete"),
            ),
        ]
    )
    nodes = pl.concat(
        [
            fixable.select(
                "fact_id",
                replacement_order.alias("rewrite_order"),
                pl.lit("target").alias("role"),
                pl.lit(0, dtype=pl.UInt64).alias("ordinal"),
                pl.col("initialization.id").alias("id"),
                pl.col("initialization.span.path").alias("path"),
                pl.col("initialization.span.start_line").cast(pl.UInt64).alias("start_line"),
                pl.col("initialization.span.start_column").cast(pl.UInt64).alias("start_column"),
                pl.col("initialization.span.end_line").cast(pl.UInt64).alias("end_line"),
                pl.col("initialization.span.end_column").cast(pl.UInt64).alias("end_column"),
                pl.col("initialization.kind").alias("kind"),
                pl.col("initialization.text").alias("text"),
            ),
            fixable.select(
                "fact_id",
                removal_order.alias("rewrite_order"),
                pl.lit("target").alias("role"),
                pl.lit(0, dtype=pl.UInt64).alias("ordinal"),
                pl.col("loop.id").alias("id"),
                pl.col("loop.span.path").alias("path"),
                pl.col("loop.span.start_line").cast(pl.UInt64).alias("start_line"),
                pl.col("loop.span.start_column").cast(pl.UInt64).alias("start_column"),
                pl.col("loop.span.end_line").cast(pl.UInt64).alias("end_line"),
                pl.col("loop.span.end_column").cast(pl.UInt64).alias("end_column"),
                pl.col("loop.kind").alias("kind"),
                pl.col("loop.text").alias("text"),
            ),
        ]
    )
    return RuleQuery.integer(
        frame,
        pl.col("value"),
        findings=FindingQuery.precise_integer(
            frame,
            pl.col("value"),
            "manual set comprehension",
            evidence=pl.col("evidence"),
        ),
        fix=FixQuery.build(
            "Build the set in one comprehension and drop the loop that filled it.",
            rewrites=rewrites,
            nodes=nodes,
        ),
    )
