import polars as pl

from .....facts import TypeAnnotationFact
from .....query import CountQuery, FindingQuery, RuleQuery
from .....table.relations import FactRelations


class TypeAnnotationTables(FactRelations[TypeAnnotationFact]):
    """Expose resolved annotations and their normalized scalar collections."""

    def annotation_values(self, field: str) -> pl.LazyFrame:
        """Return one scalar annotation collection keyed by its annotation record."""
        return self.values(f"annotations.{field}")

    def annotations(self) -> pl.LazyFrame:
        """Return every resolved annotation at its exact source location."""
        facts = self.facts().select(
            "fact_id",
            pl.col("path").alias("fact_path"),
            pl.col("start_line").alias("fact_start_line"),
            pl.col("start_column").alias("fact_start_column"),
            pl.col("end_line").alias("fact_end_line"),
            pl.col("end_column").alias("fact_end_column"),
            "evidence",
        )
        return (
            self.records("annotations")
            .join(facts, on="fact_id")
            .with_columns(
                pl.coalesce("node.span.path", "path", "fact_path").alias("path"),
                pl.coalesce("node.span.start_line", "fact_start_line")
                .cast(pl.UInt64)
                .alias("start_line"),
                pl.coalesce("node.span.start_column", "fact_start_column")
                .cast(pl.UInt64)
                .alias("start_column"),
                pl.coalesce("node.span.end_line", "fact_end_line")
                .cast(pl.UInt64)
                .alias("end_line"),
                pl.coalesce("node.span.end_column", "fact_end_column")
                .cast(pl.UInt64)
                .alias("end_column"),
            )
        )


def count_query(
    relations: TypeAnnotationTables,
    selected: pl.LazyFrame,
    measurement: str,
) -> CountQuery:
    """Return the exact source-fact count and standard precise finding."""
    frame = relations.counted(selected)
    value = pl.col("value")
    return RuleQuery.integer(
        frame,
        value,
        pl.lit(1, dtype=pl.UInt64),
        findings=FindingQuery.precise_integer(
            frame,
            value,
            measurement,
            evidence=pl.col("evidence"),
        ),
    )
