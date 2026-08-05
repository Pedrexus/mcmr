import polars as pl

from .....facts import SymbolReachFact
from .....table.relations import FactRelations


class ReachTables(FactRelations[SymbolReachFact]):
    """Expose normalized declaration reach records and their source facts."""

    @staticmethod
    def finding_rows(selected: pl.LazyFrame) -> pl.LazyFrame:
        """Project declaration spans into normalized finding location columns."""
        return selected.with_columns(
            pl.col("span.path").alias("path"),
            pl.col("span.start_line").cast(pl.UInt64).alias("start_line"),
            pl.col("span.start_column").cast(pl.UInt64).alias("start_column"),
            pl.col("span.end_line").cast(pl.UInt64).alias("end_line"),
            pl.col("span.end_column").cast(pl.UInt64).alias("end_column"),
        )

    def declarations(self) -> pl.LazyFrame:
        """Return declaration records with fact flags and ordered evidence."""
        return self.records("declarations").join(
            self.facts().select("fact_id", "language", "is_test_module", "evidence"),
            on="fact_id",
            how="left",
        )
