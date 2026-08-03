from typing import TYPE_CHECKING

import polars as pl

from ....domain.contracts import Unit
from ....query import CountQuery, FindingQuery, RuleQuery
from ....table import CallRelation, FunctionRelation, SyntaxRelation, Table

if TYPE_CHECKING:
    from ....facts import CallFact, FunctionFact, SyntaxFact


def numba_kernels(subject: Table[FunctionFact]) -> pl.LazyFrame:
    """Return module functions compiled as Numba CUDA kernels, excluding device functions."""
    decorators = subject.lazy(FunctionRelation.DECORATORS).filter(
        pl.col("decorator").str.contains(r"^(?:numba\.)?cuda\.jit(?:$|\()")
        & ~pl.col("decorator").str.contains(r"device\s*=\s*True")
    )
    return (
        subject.lazy(FunctionRelation.FUNCTIONS)
        .filter(pl.col("scope") == "module")
        .join(
            decorators.select("function_id", "decorator"),
            left_on="entity_id",
            right_on="function_id",
            how="inner",
        )
        .select(
            "entity_id",
            "name",
            "decorator",
            pl.col("definition_path").alias("path"),
            "definition_start_line",
            "definition_end_line",
        )
    )


def call_rows(subject: Table[CallFact]) -> pl.LazyFrame:
    """Return calls belonging to the selected fact rows."""
    facts = subject.lazy(CallRelation.FACTS).select("fact_id")
    return subject.lazy(CallRelation.CALLS).join(facts, on="fact_id", how="inner")


def counted_calls(
    subject: Table[CallFact],
    selected: pl.LazyFrame,
    message: pl.Expr,
    measurement: str,
) -> CountQuery:
    """Count selected calls per source file and retain each exact call as a finding."""
    facts = subject.lazy(CallRelation.FACTS)
    counts = selected.group_by("fact_id", maintain_order=True).agg(
        pl.len().cast(pl.UInt64).alias("value")
    )
    values = facts.join(counts, on="fact_id", how="left").with_columns(
        pl.col("value").fill_null(0)
    )
    evidence = (
        subject.lazy(CallRelation.EVIDENCE)
        .group_by("fact_id", maintain_order=True)
        .agg(pl.col("signal").sort_by("ordinal").alias("evidence"))
    )
    findings = selected.join(evidence, on="fact_id", how="left").with_columns(
        pl.col("node_path").alias("path"),
        pl.col("node_start_line").alias("start_line"),
        pl.col("node_start_column").alias("start_column"),
        pl.col("node_end_line").alias("end_line"),
        pl.col("node_end_column").alias("end_column"),
        pl.col("evidence").fill_null(pl.lit([], dtype=pl.List(pl.String))),
    )
    return RuleQuery.integer(
        values,
        pl.col("value"),
        findings=FindingQuery.build(
            findings,
            message,
            ((measurement, pl.lit(1), Unit.COUNT),),
            finding_order=pl.col("ordinal"),
            evidence=pl.col("evidence"),
        ),
    )


def counted_syntax(
    subject: Table[SyntaxFact],
    selected: pl.LazyFrame,
    message: pl.Expr,
    measurement: str,
) -> CountQuery:
    """Count selected syntax nodes per declaration and retain their exact spans."""
    facts = subject.lazy(SyntaxRelation.FACTS)
    counts = selected.group_by("fact_id", maintain_order=True).agg(
        pl.len().cast(pl.UInt64).alias("value")
    )
    values = facts.join(counts, on="fact_id", how="left").with_columns(
        pl.col("value").fill_null(0)
    )
    return RuleQuery.integer(
        values,
        pl.col("value"),
        findings=FindingQuery.build(
            selected,
            message,
            ((measurement, pl.lit(1), Unit.COUNT),),
            finding_order=pl.col("ordinal"),
        ),
    )
