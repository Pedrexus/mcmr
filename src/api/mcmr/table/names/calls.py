from enum import StrEnum, auto
from typing import TYPE_CHECKING

import polars as pl

from ..runtime.candidates import CandidateRelations

if TYPE_CHECKING:
    from ...facts.foundation import Fact
    from ..runtime.table import Table


class CallRelation(StrEnum):
    """Build one contextual candidate for each resolved call site."""

    FACTS = auto()
    CALLS = auto()
    KEYWORDS = auto()
    EXPRESSIONS = auto()
    EXPRESSION_ANCESTRY = auto()
    MAPPING_ENTRIES = auto()
    MODULE_BINDINGS = auto()
    EVIDENCE = auto()

    @classmethod
    def candidates[Family: Fact](cls, table: Table[Family]) -> pl.LazyFrame:
        """Project call identity, nested expressions, and keyword names without JSON facts."""
        modules = table.lazy(CallRelation.FACTS).select(
            "fact_order",
            pl.col("fact_id").alias("module_fact_id"),
            "language",
            "is_test",
        )
        calls = table.lazy(CallRelation.CALLS).join(
            modules,
            left_on="fact_id",
            right_on="module_fact_id",
            how="inner",
        )
        facts = calls.select(
            "fact_order",
            pl.col("call_id").alias("fact_id"),
            pl.col("node_path").alias("path"),
            pl.col("node_start_line").cast(pl.UInt64).alias("start_line"),
            pl.col("node_start_column").cast(pl.UInt64).alias("start_column"),
            pl.col("node_end_line").cast(pl.UInt64).alias("end_line"),
            pl.col("node_end_column").cast(pl.UInt64).alias("end_column"),
            "language",
            "qualified_name",
            "target_id",
            "assigned_target",
            "result_is_discarded",
            "is_external",
            "is_standard_library",
            "is_first_party",
            "is_constructor",
            "is_shadowed",
            "has_ambiguous_alias",
            "is_decorator_factory",
            "has_starred_arguments",
            "enclosing_is_async",
            "is_test",
            "node_text",
        )
        identity = calls.select("call_id", "fact_order")
        records = (
            table.lazy(CallRelation.EXPRESSIONS)
            .join(identity, on="call_id", how="inner")
            .select(
                "fact_order",
                pl.col("call_id").alias("fact_id"),
                pl.lit("expressions").alias("relation"),
                pl.col("call_id").alias("parent_id"),
                pl.col("expression_id").alias("record_id"),
                pl.col("preorder").cast(pl.UInt64).alias("ordinal"),
                pl.lit(None, dtype=pl.Float64).alias("confidence"),
                pl.lit(None, dtype=pl.String).alias("detail"),
                pl.lit(None, dtype=pl.String).alias("signal"),
                pl.lit(None, dtype=pl.String).alias("source"),
                "depth",
                "literal_kind",
                "qualified_name",
                pl.col("relation").alias("expression_relation"),
                "resolved_type",
                "root_ordinal",
                "root_relation",
                "text",
                pl.lit(0).alias("candidate_order_0"),
                pl.col("preorder").alias("candidate_order_1"),
                pl.lit(0).alias("candidate_order_2"),
                pl.lit(0).alias("candidate_order_3"),
            )
        )
        keyword_values = (
            table.lazy(CallRelation.KEYWORDS)
            .join(identity, on="call_id", how="inner")
            .select(
                "fact_order",
                pl.col("call_id").alias("fact_id"),
                pl.col("call_id").alias("parent_id"),
                "ordinal",
                pl.col("name").alias("value"),
                pl.lit(0).alias("candidate_order_0"),
                pl.col("ordinal").alias("candidate_order_1"),
                pl.lit(0).alias("candidate_order_2"),
                pl.lit(0).alias("candidate_order_3"),
            )
        )
        return CandidateRelations(
            facts=facts,
            records=records,
            values=CandidateRelations.value_rows(keyword_values, "keyword_names"),
        ).candidates()
