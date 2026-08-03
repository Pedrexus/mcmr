import polars as pl
from pydantic import NonNegativeInt

from ...... import rule
from ......domain.contracts import (
    FixSafety,
    Unit,
)
from ......facts import CallFact
from ......query import CountQuery, FindingQuery, FixQuery, RuleQuery
from ......table import CallRelation, Table


@rule("PY-ASYN0005", fix_safety=FixSafety.SAFE)
def deprecated_asyncio_coroutine_function_check(
    subject: Table[CallFact],
    *,
    python_minor: NonNegativeInt = 14,
) -> CountQuery:
    """Count the coroutine function alias deprecated in Python 3.14.

    Definition
    ----------
    For a configured minimum Python 3 minor version of 14 or newer, resolve qualified,
    directly imported, and aliased references to `asyncio.iscoroutinefunction`. The result
    value and findings count every reference. Use `inspect.iscoroutinefunction` instead.

    Evidence
    --------
    Every finding identifies the exact deprecated reference and source range. The value is the
    number of deprecated alias references.

    Exceptions
    ----------
    A compatibility package that deliberately exposes the old spelling can exclude its
    compatibility module. Ordinary callers need no behavior change because the asyncio name is an
    alias of the inspect implementation. No automatic fix is offered until import edits can
    preserve aliases and remove newly unused imports safely. `python_minor` is the Python 3 minor
    version the project targets, and the rule reports nothing below 14 because the alias is not
    deprecated there.

    Examples
    --------
    `asyncio.iscoroutinefunction(callback)` is reported. So is
    `from asyncio import iscoroutinefunction as is_async`. Importing `inspect` and calling
    `inspect.iscoroutinefunction(callback)` is accepted. A Python 3.13 configuration produces
    no finding.

    References
    ----------
    Cites "What's New In Python"
    https://docs.python.org/3.14/deprecations/
    Cites "The Python Standard Library", inspect coroutine function predicate
    https://docs.python.org/3.14/library/inspect.html#inspect.iscoroutinefunction
    """
    facts = subject.lazy(CallRelation.FACTS)
    evidence = (
        subject.lazy(CallRelation.EVIDENCE)
        .group_by("fact_id", maintain_order=True)
        .agg(pl.col("signal").sort_by("ordinal").alias("evidence"))
    )
    selected = (
        subject.lazy(CallRelation.CALLS)
        .join(facts.select("fact_id"), on="fact_id", how="inner")
        .filter(
            pl.lit(python_minor >= 14)
            & (pl.col("qualified_name") == "asyncio.iscoroutinefunction")
        )
    )
    counts = selected.group_by("fact_id", maintain_order=True).agg(
        pl.len().cast(pl.UInt64).alias("value")
    )
    frame = facts.join(counts, on="fact_id", how="left").with_columns(pl.col("value").fill_null(0))
    finding_rows = (
        selected.select(
            "fact_id",
            "ordinal",
            pl.col("node_path").alias("path"),
            pl.col("node_start_line").alias("start_line"),
            pl.col("node_start_column").alias("start_column"),
            pl.col("node_end_line").alias("end_line"),
            pl.col("node_end_column").alias("end_column"),
        )
        .join(evidence, on="fact_id", how="left")
        .with_columns(pl.col("evidence").fill_null(pl.lit([], dtype=pl.List(pl.String))))
    )
    repairable = selected.filter(pl.col("callee_id").is_not_null())
    rewrites = repairable.select(
        "fact_id",
        pl.col("ordinal").alias("rewrite_order"),
        pl.lit("replace").alias("kind"),
        pl.lit("inspect.iscoroutinefunction").alias("source"),
        pl.lit("").alias("placement"),
        pl.lit("").alias("name"),
        pl.lit("").alias("symbol_id"),
        pl.lit("").alias("symbol_name"),
        pl.lit(False).alias("references_complete"),
    )
    nodes = repairable.select(
        "fact_id",
        pl.col("ordinal").alias("rewrite_order"),
        pl.lit("target").alias("role"),
        pl.lit(0, dtype=pl.UInt64).alias("ordinal"),
        pl.col("callee_id").alias("id"),
        pl.col("callee_path").alias("path"),
        pl.col("callee_start_line").alias("start_line"),
        pl.col("callee_start_column").alias("start_column"),
        pl.col("callee_end_line").alias("end_line"),
        pl.col("callee_end_column").alias("end_column"),
        pl.col("callee_kind").alias("kind"),
        pl.col("callee_text").alias("text"),
    )
    imports = repairable.select(
        "fact_id",
        pl.col("ordinal").alias("rewrite_order"),
        pl.lit(0, dtype=pl.UInt64).alias("ordinal"),
        pl.lit("inspect").alias("module"),
        pl.lit("").alias("name"),
        pl.lit("").alias("alias"),
        pl.lit(0, dtype=pl.UInt64).alias("level"),
        pl.lit(False).alias("type_only"),
    )
    value = pl.col("value")
    return RuleQuery.integer(
        frame,
        value,
        findings=FindingQuery.build(
            finding_rows,
            pl.lit(
                "`asyncio.iscoroutinefunction` is deprecated in favor of "
                "`inspect.iscoroutinefunction`"
            ),
            (("deprecated asyncio coroutine function check", pl.lit(1), Unit.COUNT),),
            finding_order=pl.col("ordinal"),
            evidence=pl.col("evidence"),
        ),
        fix=FixQuery.build(
            "Point each deprecated check at the `inspect` function that replaced it.",
            rewrites=rewrites,
            nodes=nodes,
            imports=imports,
        ),
    )
