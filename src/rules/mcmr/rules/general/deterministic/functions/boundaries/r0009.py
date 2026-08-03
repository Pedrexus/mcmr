import polars as pl

from ...... import rule
from ......domain.contracts import FixSafety
from ......facts import FunctionFact
from ......query import FindingQuery, FixQuery, RuleQuery
from ......table import FunctionRelation, Table


@rule("ALL-FUNC0005", fix_safety=FixSafety.REVIEW)
def transparent_unary_wrapper(subject: Table[FunctionFact]) -> RuleQuery[bool]:
    """Detect a public unary function that only forwards one argument.

    Definition
    ----------
    Report a synchronous public module function or static method only when it has one required
    parameter and its sole executable statement returns one call with that parameter unchanged.
    A direct callable alias or direct call expresses the same dispatch without another boundary.

    Evidence
    --------
    Each finding identifies the wrapper, forwarded callable, and complete source range. The rule
    does not infer semantic similarity or inspect nested behavior.

    Exceptions
    ----------
    Instance methods, class methods, private helpers, asynchronous adapters, decorators other than
    `staticmethod`, overloads, defaults, argument adaptation, result transformation, and recursive
    calls are excluded. A narrowing annotation alone does not preserve a wrapper when the called
    function already exposes the same narrowing contract. Keep a wrapper when its distinct
    `__name__`, signature, documentation, instrumentation, or compatibility boundary is an
    intentional public contract.

    Examples
    --------
    Bad
    ~~~
    `def normalize(value: str) -> str: return inflection.underscore(value)` adds only a forwarding
    frame.

    Good
    ~~~~
    `normalize = inflection.underscore` gives the callable a project name directly. A function
    that validates, transforms, logs, awaits, or combines arguments remains a real boundary.
    Inside a method, call `inspect.isclass(value)` directly instead of wrapping it as `is_class`.

    References
    ----------
    Cites "The Python Language Reference", assignment statements
    https://docs.python.org/3/reference/simple_stmts.html#assignment-statements
    Cites "A Philosophy of Software Design", chapters 4 and 7
    Cites "Clean Code", chapter 3
    """
    parameters = (
        subject.lazy(FunctionRelation.PARAMETERS)
        .group_by("function_id")
        .agg(pl.len().cast(pl.UInt64).alias("parameter_count"))
    )
    decorators = (
        subject.lazy(FunctionRelation.DECORATORS)
        .group_by("function_id")
        .agg((pl.col("decorator") != "staticmethod").any().alias("has_other_decorator"))
    )
    frame = (
        subject.lazy(FunctionRelation.FUNCTIONS)
        .join(parameters, left_on="entity_id", right_on="function_id", how="left")
        .join(decorators, left_on="entity_id", right_on="function_id", how="left")
        .with_columns(
            pl.col("parameter_count").fill_null(0),
            pl.col("has_other_decorator").fill_null(False),
        )
    )
    value = (
        pl.col("scope").is_in(["module", "method"])
        & (pl.col("visibility") == "public")
        & ~pl.col("is_async")
        & ~pl.col("has_other_decorator")
        & (pl.col("parameter_count") == 1)
        & pl.col("returns_single_call")
        & pl.col("forwards_only_parameter_unchanged")
        & ~pl.col("is_overload")
        & ~pl.col("is_recursive")
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
        findings=FindingQuery.precise_boolean(frame, value, "transparent unary wrapper"),
        fix=fix,
    )
