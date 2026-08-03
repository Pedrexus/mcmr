from typing import TYPE_CHECKING

import polars as pl

from ....table import GenericRelation
from ..generic.relations import CandidateRelations

if TYPE_CHECKING:
    from ....facts.foundation import Fact
    from ....table import Table


class CommentCandidateRelations(CandidateRelations):
    """Build one contextual candidate for each concrete comment group."""

    @classmethod
    def comments[Family: Fact](cls, table: Table[Family]) -> CandidateRelations:
        """Project comment records into independently addressable model subjects."""
        module = table.lazy(GenericRelation.FACTS).select(
            pl.col("fact_id").alias("module_fact_id"),
            "language",
            pl.col("path").alias("module_path"),
            pl.col("start_line").alias("module_start_line"),
            pl.col("start_column").alias("module_start_column"),
            pl.col("end_line").alias("module_end_line"),
            pl.col("end_column").alias("module_end_column"),
        )
        groups = table.lazy(GenericRelation.RECORDS).filter(pl.col("relation") == "groups")
        facts = groups.join(
            module,
            left_on="fact_id",
            right_on="module_fact_id",
            how="inner",
        ).select(
            "fact_order",
            pl.col("record_id").alias("fact_id"),
            pl.coalesce("node.span.path", "module_path").alias("path"),
            pl.coalesce("node.span.start_line", "module_start_line")
            .cast(pl.UInt64)
            .alias("start_line"),
            pl.coalesce("node.span.start_column", "module_start_column")
            .cast(pl.UInt64)
            .alias("start_column"),
            pl.coalesce("node.span.end_line", "module_end_line").cast(pl.UInt64).alias("end_line"),
            pl.coalesce("node.span.end_column", "module_end_column")
            .cast(pl.UInt64)
            .alias("end_column"),
            "language",
            "text",
            "preceding_source",
            "following_source",
            "line_count",
            "character_count",
            "token_count",
            "parses_as_source",
            "is_directive",
            "is_documentation",
        )
        empty_records = groups.filter(pl.lit(False)).with_columns(
            pl.col("record_id").alias("fact_id")
        )
        empty_values = table.lazy(GenericRelation.VALUES).filter(pl.lit(False))
        return cls(facts=facts, records=empty_records, values=empty_values)
