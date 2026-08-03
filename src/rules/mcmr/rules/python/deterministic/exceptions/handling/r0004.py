import polars as pl

from ...... import rule
from ......domain.contracts import FixSafety
from ......facts import TryBlockFact
from ......query import CountQuery, FindingQuery, FixQuery, RuleQuery
from ......table import Table


@rule("PY-EXCE0004", fix_safety=FixSafety.SAFE)
def nullable_exception_return_suppression(subject: Table[TryBlockFact]) -> CountQuery:
    """Use `suppress` when one guarded return maps an exception to `None`.

    Definition
    ----------
    Report an ordinary `try` whose protected body is exactly one value-returning statement and
    whose sole handler catches one non-tuple exception type and returns `None`. Replace the whole
    statement with a `contextlib.suppress` block that keeps the successful return and an explicit
    fallback return. This states the nullable result without a handler whose only action is the
    absence of a value.

    Evidence
    --------
    Retain the complete `try`, its one protected return, the caught expression, and the handler's
    one `return None`. The emitted value is the number of exact regions in each file.

    Exceptions
    ----------
    Keep exception groups, tuple catches, bound exception aliases, multiple handlers, `else` or
    `finally` clauses, multiple protected statements, multiple handler statements, multiline
    returns, and handlers that perform any action besides returning `None`. Those shapes need a
    wider control-flow proof and receive no suggestion from this rule.

    Examples
    --------
    A `try` holding `return parse(value)` followed by an `except ValidationError` holding
    `return None` becomes a `with suppress(ValidationError)` guarded return followed by
    `return None`.

    References
    ----------
    Adapts Ruff SIM105 suppressible-exception
    https://docs.astral.sh/ruff/rules/suppressible-exception/
    Cites "The Python Standard Library", contextlib suppress
    https://docs.python.org/3.14/library/contextlib.html#contextlib.suppress
    """
    relations = subject
    protected = (
        relations.records("regions.protected_statements")
        .group_by("fact_id", "parent_id", maintain_order=True)
        .agg(
            pl.len().alias("protected_count"),
            pl.col("kind").first().alias("protected_kind"),
            pl.col("text").first().alias("protected_text"),
        )
    )
    bodies = (
        relations.records("regions.handlers.body")
        .group_by("fact_id", "parent_id", maintain_order=True)
        .agg(
            pl.len().alias("handler_body_count"),
            pl.col("kind").first().alias("handler_body_kind"),
            pl.col("text").first().alias("handler_body_text"),
        )
    )
    handlers = (
        relations.records("regions.handlers")
        .join(
            bodies,
            left_on=["fact_id", "record_id"],
            right_on=["fact_id", "parent_id"],
            how="left",
        )
        .group_by("fact_id", "parent_id", maintain_order=True)
        .agg(
            pl.len().alias("handler_count"),
            pl.col("caught").first().alias("handler_caught"),
            pl.col("caught_is_tuple").first().alias("handler_caught_is_tuple"),
            pl.col("alias").first().alias("handler_alias"),
            pl.col("handler_body_count").first(),
            pl.col("handler_body_kind").first(),
            pl.col("handler_body_text").first(),
        )
    )
    selected = (
        relations.records("regions")
        .join(
            protected,
            left_on=["fact_id", "record_id"],
            right_on=["fact_id", "parent_id"],
            how="left",
        )
        .join(
            handlers,
            left_on=["fact_id", "record_id"],
            right_on=["fact_id", "parent_id"],
            how="left",
        )
        .filter(
            ~pl.col("is_exception_group")
            & ~pl.col("has_else")
            & ~pl.col("has_finally")
            & (pl.col("protected_count") == 1)
            & (pl.col("protected_kind") == "return")
            & pl.col("protected_text").str.starts_with("return ")
            & ~pl.col("protected_text").str.contains("\n", literal=True)
            & (pl.col("handler_count") == 1)
            & (pl.col("handler_caught") != "")
            & ~pl.col("handler_caught_is_tuple")
            & (pl.col("handler_alias") == "")
            & (pl.col("handler_body_count") == 1)
            & (pl.col("handler_body_kind") == "return")
            & pl.col("handler_body_text").is_in(["return", "return None"])
            & pl.col("statement.id").is_not_null()
        )
        .sort("fact_order", "ordinal")
        .with_row_index("rewrite_order")
        .with_columns(pl.col("rewrite_order").cast(pl.UInt64))
    )
    rewrites = selected.select(
        "fact_id",
        "rewrite_order",
        pl.lit("replace").alias("kind"),
        pl.concat_str(
            pl.lit("with suppress("),
            pl.col("handler_caught"),
            pl.lit("):\n    "),
            pl.col("protected_text"),
            pl.lit("\nreturn None"),
        ).alias("source"),
        pl.lit("").alias("placement"),
        pl.lit("").alias("name"),
        pl.lit("").alias("symbol_id"),
        pl.lit("").alias("symbol_name"),
        pl.lit(False).alias("references_complete"),
    )
    nodes = selected.select(
        "fact_id",
        "rewrite_order",
        pl.lit("target").alias("role"),
        pl.lit(0, dtype=pl.UInt64).alias("ordinal"),
        pl.col("statement.id").alias("id"),
        pl.col("statement.span.path").alias("path"),
        pl.col("statement.span.start_line").cast(pl.UInt64).alias("start_line"),
        pl.col("statement.span.start_column").cast(pl.UInt64).alias("start_column"),
        pl.col("statement.span.end_line").cast(pl.UInt64).alias("end_line"),
        pl.col("statement.span.end_column").cast(pl.UInt64).alias("end_column"),
        pl.col("statement.kind").alias("kind"),
        pl.col("statement.text").alias("text"),
    )
    imports = selected.select(
        "fact_id",
        "rewrite_order",
        pl.lit(0, dtype=pl.UInt64).alias("ordinal"),
        pl.lit("contextlib").alias("module"),
        pl.lit("suppress").alias("name"),
        pl.lit("").alias("alias"),
        pl.lit(0, dtype=pl.UInt64).alias("level"),
        pl.lit(False).alias("type_only"),
    )
    frame = relations.counted(selected)
    return RuleQuery.integer(
        frame,
        pl.col("value"),
        findings=FindingQuery.precise_integer(
            frame,
            pl.col("value"),
            "nullable exception return",
            evidence=pl.col("evidence"),
        ),
        fix=FixQuery.build(
            "Express the nullable return through `contextlib.suppress`.",
            rewrites=rewrites,
            nodes=nodes,
            imports=imports,
        ),
    )
