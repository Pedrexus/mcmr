from typing import TYPE_CHECKING

import polars as pl

from ....facts import RustSurfaceFact
from ....table.relations import FactRelations

if TYPE_CHECKING:
    from ....table import Table


class RustRelations(FactRelations[RustSurfaceFact]):
    """Expose normalized Rust ownership and lifetime relations."""

    def __init__(self, subject: Table[RustSurfaceFact]) -> None:
        super().__init__(subject)

    def annotations(self) -> pl.LazyFrame:
        """Return lifetime annotations with their names rendered in source order."""
        names = (
            self.values("annotations.names")
            .with_columns(
                pl.concat_str(
                    pl.lit("`'"),
                    pl.col("string_value"),
                    pl.lit("`"),
                ).alias("stated_name")
            )
            .group_by("parent_id", maintain_order=True)
            .agg(pl.col("stated_name").sort_by("ordinal").str.join(", ").alias("stated_names"))
        )
        return (
            self.records("annotations")
            .join(
                names,
                left_on="record_id",
                right_on="parent_id",
                how="left",
            )
            .with_columns(pl.col("stated_names").fill_null(""))
        )

    def located(self, records: pl.LazyFrame) -> pl.LazyFrame:
        """Attach fact context and use each record's line as its finding span."""
        return records.join(
            self.facts(),
            on=["fact_order", "fact_id"],
            how="inner",
        ).with_columns(
            pl.col("line").alias("start_line"),
            pl.lit(0, dtype=pl.UInt64).alias("start_column"),
            pl.col("line").alias("end_line"),
            pl.lit(0, dtype=pl.UInt64).alias("end_column"),
        )
