import polars as pl

from ......facts import TestCaseGroupFact
from ......table.relations import FactRelations


class TestCaseTables(FactRelations[TestCaseGroupFact]):
    """Expose sibling case groups, literal vectors, and manual case loops."""

    def groups(self) -> pl.LazyFrame:
        """Return every sibling test group."""
        return self.records("groups")

    def loops(self) -> pl.LazyFrame:
        """Return every test-owned literal loop."""
        return self.records("loops")

    def vector_counts(self) -> pl.LazyFrame:
        """Count literal vectors and their exact distinct ordered values per group."""
        values = self.values("groups.literal_vectors")
        containers = values.filter(pl.col("entry_kind") == "container").select(
            pl.col("parent_id").alias("record_id"),
            "container_id",
            "container_ordinal",
        )
        vector_values = (
            values.filter(pl.col("entry_kind") == "value")
            .group_by("container_id", maintain_order=True)
            .agg(pl.col("string_value").sort_by("ordinal").alias("vector"))
        )
        vectors = containers.join(vector_values, on="container_id", how="left").with_columns(
            pl.col("vector").fill_null(pl.lit([], dtype=pl.List(pl.String)))
        )
        return vectors.group_by("record_id", maintain_order=True).agg(
            pl.len().cast(pl.UInt64).alias("vector_count"),
            pl.col("vector").n_unique().cast(pl.UInt64).alias("distinct_vector_count"),
        )
