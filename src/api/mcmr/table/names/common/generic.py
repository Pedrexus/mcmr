from enum import StrEnum, auto
from typing import TYPE_CHECKING

import polars as pl

from ...runtime.candidates import CandidateRelations

if TYPE_CHECKING:
    from ....facts.foundation import Fact
    from ...runtime.table import Table


class GenericRelation(StrEnum):
    """Name the universal relations of each schema-normalized fact family."""

    FACTS = auto()
    RECORDS = auto()
    VALUES = auto()

    @classmethod
    def candidates[Family: Fact](cls, table: Table[Family]) -> pl.LazyFrame:
        """Build generic or comment-granular contextual candidates."""
        relations = (
            cls._comments(table)
            if table.family.__name__ == "CommentFact"
            and "node.text" in table.frame(cls.RECORDS).columns
            else CandidateRelations(
                facts=table.lazy(cls.FACTS),
                records=table.lazy(cls.RECORDS),
                values=table.lazy(cls.VALUES),
            )
        )
        return relations.candidates()

    @classmethod
    def _comments[Family: Fact](cls, table: Table[Family]) -> CandidateRelations:
        """Project comment groups into independently addressable model subjects."""
        module = table.lazy(cls.FACTS).select(
            pl.col("fact_id").alias("module_fact_id"),
            "language",
            pl.col("path").alias("module_path"),
            pl.col("start_line").alias("module_start_line"),
            pl.col("start_column").alias("module_start_column"),
            pl.col("end_line").alias("module_end_line"),
            pl.col("end_column").alias("module_end_column"),
        )
        groups = table.lazy(cls.RECORDS).filter(pl.col("relation") == "groups")
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
        return CandidateRelations(
            facts=facts,
            records=groups.filter(pl.lit(False)).with_columns(
                pl.col("record_id").alias("fact_id")
            ),
            values=table.lazy(cls.VALUES).filter(pl.lit(False)),
        )
