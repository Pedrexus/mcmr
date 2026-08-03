import polars as pl

from .....domain.contracts import Unit
from .....facts import QueryFact
from .....query import CountQuery, FindingQuery, RuleQuery
from .....table.relations import FactRelations


class QueryTables(FactRelations[QueryFact]):
    """Expose normalized query operations and their owning source facts."""

    @staticmethod
    def finding_rows(selected: pl.LazyFrame) -> pl.LazyFrame:
        """Project operation nodes into the normalized finding location columns."""
        return selected.with_columns(
            pl.col("node.span.path").alias("path"),
            pl.col("node.span.start_line").cast(pl.UInt64).alias("start_line"),
            pl.col("node.span.start_column").cast(pl.UInt64).alias("start_column"),
            pl.col("node.span.end_line").cast(pl.UInt64).alias("end_line"),
            pl.col("node.span.end_column").cast(pl.UInt64).alias("end_column"),
        )

    @staticmethod
    def rewrite_node(
        selected: pl.LazyFrame,
        prefix: str,
        rewrite_order: pl.Expr,
    ) -> pl.LazyFrame:
        """Project one flattened operation node into a target rewrite relation."""
        return selected.select(
            "fact_id",
            rewrite_order.cast(pl.UInt64).alias("rewrite_order"),
            pl.lit("target").alias("role"),
            pl.lit(0, dtype=pl.UInt64).alias("ordinal"),
            pl.col(f"{prefix}.id").alias("id"),
            pl.col(f"{prefix}.span.path").alias("path"),
            pl.col(f"{prefix}.span.start_line").cast(pl.UInt64).alias("start_line"),
            pl.col(f"{prefix}.span.start_column").cast(pl.UInt64).alias("start_column"),
            pl.col(f"{prefix}.span.end_line").cast(pl.UInt64).alias("end_line"),
            pl.col(f"{prefix}.span.end_column").cast(pl.UInt64).alias("end_column"),
            pl.col(f"{prefix}.kind").alias("kind"),
            pl.col(f"{prefix}.text").alias("text"),
        )

    def operations(self) -> pl.LazyFrame:
        """Return resolved database operation records in source order."""
        return self.records("operations").join(
            self.facts().select("fact_id", "evidence"), on="fact_id", how="left"
        )


def count_query(
    relations: QueryTables,
    selected: pl.LazyFrame,
    *,
    message: str,
    measurement: str,
) -> CountQuery:
    """Return one precise finding for each selected database operation."""
    frame = relations.counted(selected)
    findings = FindingQuery.build(
        relations.finding_rows(selected),
        pl.lit(message),
        ((measurement, pl.lit(1), Unit.COUNT),),
        finding_order=pl.col("ordinal"),
        evidence=pl.col("evidence"),
    )
    return RuleQuery.integer(frame, pl.col("value"), findings=findings)
