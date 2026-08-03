import polars as pl

from .....domain.contracts import Unit
from .....facts import RouteFact
from .....query import CountQuery, FindingQuery, RuleQuery
from .....table.relations import FactRelations


class RouteTables(FactRelations[RouteFact]):
    """Expose declared routes and their nested client references."""

    def routes(self) -> pl.LazyFrame:
        """Return declared routes with their source span and provider evidence."""
        return (
            self.records("routes")
            .join(self.facts().select("fact_id", "evidence"), on="fact_id", how="left")
            .with_columns(
                pl.col("path").alias("route_path"),
                pl.col("declared_in").alias("finding_path"),
                pl.col("line").cast(pl.UInt64).alias("finding_start_line"),
                pl.lit(0, dtype=pl.UInt64).alias("finding_start_column"),
                pl.col("line").cast(pl.UInt64).alias("finding_end_line"),
                pl.lit(0, dtype=pl.UInt64).alias("finding_end_column"),
            )
        )

    def summed(self, selected: pl.LazyFrame) -> pl.LazyFrame:
        """Sum selected route contributions onto every repository fact."""
        counts = selected.group_by("fact_id", maintain_order=True).agg(
            pl.col("amount").sum().cast(pl.UInt64).alias("value"),
            pl.len().cast(pl.UInt64).alias("finding_count"),
        )
        return (
            self.facts()
            .join(counts, on="fact_id", how="left")
            .with_columns(pl.col("value", "finding_count").fill_null(0))
        )


def count_query(
    relations: RouteTables,
    selected: pl.LazyFrame,
    message: pl.Expr,
    measurement: str,
) -> CountQuery:
    """Return exact located route findings and their summed count."""
    findings = FindingQuery.build(
        selected.with_columns(
            pl.col("finding_path").alias("path"),
            pl.col("finding_start_line").alias("start_line"),
            pl.col("finding_start_column").alias("start_column"),
            pl.col("finding_end_line").alias("end_line"),
            pl.col("finding_end_column").alias("end_column"),
        ),
        message,
        ((measurement, pl.col("amount"), Unit.COUNT),),
        finding_order=pl.col("finding_order"),
        evidence=pl.col("evidence"),
    )
    return RuleQuery.integer(
        relations.summed(selected),
        pl.col("value"),
        pl.col("finding_count"),
        findings=findings,
    )
