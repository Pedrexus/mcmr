from typing import TYPE_CHECKING

import polars as pl

if TYPE_CHECKING:
    from .....facts import CommentFact
    from .....table.relations import FactRelations


def comment_groups(relations: FactRelations[CommentFact]) -> pl.LazyFrame:
    """Return every comment group with a complete fallback finding span."""
    facts = relations.facts().select(
        "fact_id",
        pl.col("path").alias("fact_path"),
        pl.col("start_line").alias("fact_start_line"),
        pl.col("start_column").alias("fact_start_column"),
        pl.col("end_line").alias("fact_end_line"),
        pl.col("end_column").alias("fact_end_column"),
        "evidence",
    )
    return (
        relations.records("groups")
        .join(facts, on="fact_id", how="left")
        .with_columns(
            pl.coalesce("node.span.path", "fact_path").alias("path"),
            pl.coalesce("node.span.start_line", "fact_start_line")
            .cast(pl.UInt64)
            .alias("start_line"),
            pl.coalesce("node.span.start_column", "fact_start_column")
            .cast(pl.UInt64)
            .alias("start_column"),
            pl.coalesce("node.span.end_line", "fact_end_line").cast(pl.UInt64).alias("end_line"),
            pl.coalesce("node.span.end_column", "fact_end_column")
            .cast(pl.UInt64)
            .alias("end_column"),
        )
    )


def ordered(frame: pl.LazyFrame) -> pl.LazyFrame:
    """Attach stable per-fact finding order to selected comment rows."""
    return frame.sort("fact_order", "ordinal").with_columns(
        pl.int_range(pl.len()).over("fact_id").cast(pl.UInt64).alias("finding_order")
    )


def four_significant_digits(value: pl.Expr) -> pl.Expr:
    """Format a percentage like Python's four-significant-digit general format."""
    rounded = value.round_sig_figs(4)
    plain = rounded.cast(pl.String).str.replace(r"\.0$", "")
    exponent = rounded.abs().replace(0.0, 1.0).log10().floor().cast(pl.Int64)
    mantissa = (rounded / pl.lit(10.0).pow(exponent)).round_sig_figs(4)
    scientific = pl.concat_str(
        mantissa.cast(pl.String).str.replace(r"\.0$", ""),
        pl.lit("e-"),
        exponent.abs().cast(pl.String).str.pad_start(2, "0"),
    )
    return (
        pl.when(rounded == 0)
        .then(pl.lit("0"))
        .when(rounded.abs() < 0.0001)
        .then(scientific)
        .otherwise(plain)
    )
