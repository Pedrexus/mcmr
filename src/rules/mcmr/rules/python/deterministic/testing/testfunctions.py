import polars as pl

from .....facts import TestFunctionFact
from .....table.relations import FactRelations


class TestFunctionTables(FactRelations[TestFunctionFact]):
    """Expose collected tests and their nested normalized relations."""

    def behaviors(self) -> pl.LazyFrame:
        """Return collected tests with their ordered fixtures, assertions, literals, and reach."""
        frame = self.collected()
        for relation in (
            "fixture_names",
            "assertion_shapes",
            "literal_values",
            "direct_targets",
            "reachable_targets",
        ):
            frame = frame.join(
                self.strings(relation),
                on=["fact_id", "record_id"],
                how="left",
            ).with_columns(pl.col(relation).fill_null(pl.lit([], dtype=pl.List(pl.String))))
        return frame

    def calls(self) -> pl.LazyFrame:
        """Return resolved calls nested directly under retained tests."""
        return self.records("tests.calls")

    def collected(self) -> pl.LazyFrame:
        """Return only tests Pytest's default conventions collect."""
        return self.tests().filter(pl.col("is_collected"))

    def collected_maximum(self, column: str) -> pl.LazyFrame:
        """Attach one collected-test maximum and its exact definition to every source fact."""
        maximum = (
            self.collected()
            .sort(["fact_id", column, "ordinal"], descending=[False, True, False])
            .group_by("fact_id", maintain_order=True)
            .agg(
                pl.col(column).first().alias("value"),
                pl.col("node.span.path").first().alias("test_path"),
                pl.col("node.span.start_line").first().alias("test_start_line"),
                pl.col("node.span.start_column").first().alias("test_start_column"),
                pl.col("node.span.end_line").first().alias("test_end_line"),
                pl.col("node.span.end_column").first().alias("test_end_column"),
            )
        )
        return (
            self.facts()
            .join(maximum, on="fact_id", how="left")
            .with_columns(
                pl.col("value").fill_null(0),
                pl.coalesce("test_path", "path").alias("path"),
                pl.coalesce(pl.col("test_start_line").cast(pl.UInt64), "start_line").alias(
                    "start_line"
                ),
                pl.coalesce(pl.col("test_start_column").cast(pl.UInt64), "start_column").alias(
                    "start_column"
                ),
                pl.coalesce(pl.col("test_end_line").cast(pl.UInt64), "end_line").alias("end_line"),
                pl.coalesce(pl.col("test_end_column").cast(pl.UInt64), "end_column").alias(
                    "end_column"
                ),
            )
        )

    def strings(self, relation: str) -> pl.LazyFrame:
        """Return one ordered list of strings for every retained test record."""
        return (
            self.values(f"tests.{relation}")
            .filter(pl.col("entry_kind") == "value")
            .group_by("fact_id", "parent_id", maintain_order=True)
            .agg(pl.col("string_value").sort_by("ordinal").alias(relation))
            .rename({"parent_id": "record_id"})
        )

    def tests(self) -> pl.LazyFrame:
        """Return every test retained by the provider."""
        return self.records("tests")
