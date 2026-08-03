import polars as pl

from .....facts import CloneGroupFact
from .....table.relations import FactRelations


class CloneTables(FactRelations[CloneGroupFact]):
    """Expose clone fragments and the group measures derived from their geometry."""

    def fragments(self) -> pl.LazyFrame:
        """Return every clone fragment in provider order."""
        return self.records("fragments")

    def groups(self) -> pl.LazyFrame:
        """Attach copy, line, and redundant-line counts to every clone group."""
        geometry = (
            self.fragments()
            .group_by("fact_id", maintain_order=True)
            .agg(
                pl.len().cast(pl.UInt64).alias("copy_count"),
                (pl.col("end_line") - pl.col("start_line") + 1)
                .min()
                .cast(pl.UInt64)
                .alias("line_count"),
            )
        )
        return (
            self.facts()
            .join(geometry, on="fact_id", how="inner")
            .with_columns(
                (pl.col("line_count") * (pl.col("copy_count") - 1)).alias("redundant_line_count")
            )
        )
