from typing import TYPE_CHECKING

import polars as pl

from .....facts import OverrideFact
from .....query import CountQuery, FindingQuery, OccurrenceQuery, RuleQuery
from .....table.relations import FactRelations

if TYPE_CHECKING:
    from .....table import Table


class OverrideTables(FactRelations[OverrideFact]):
    """Expose the normalized inheritance relations shared by override rules."""

    def __init__(self, subject: Table[OverrideFact]) -> None:
        super().__init__(subject)

    def members(self, relation: str) -> pl.LazyFrame:
        """Return declared or inherited members with useful decorator predicates."""
        decorators = self.values(f"{relation}.decorators")
        flags = decorators.group_by("parent_id").agg(
            pl.col("string_value")
            .str.split(".")
            .list.last()
            .eq("classmethod")
            .any()
            .alias("is_classmethod"),
            pl.col("string_value").str.ends_with(".setter").any().alias("is_setter"),
            (
                pl.col("string_value")
                .str.split(".")
                .list.last()
                .is_in(
                    [
                        "abstractmethod",
                        "abstractproperty",
                        "abstractclassmethod",
                        "abstractstaticmethod",
                    ]
                )
                .any()
            ).alias("is_promised"),
            (
                pl.col("string_value")
                .str.split(".")
                .list.last()
                .is_in(["property", "cached_property"])
                .any()
                | pl.col("string_value").str.contains(r"\.(setter|getter|deleter)$").any()
            ).alias("is_read_as_data"),
            pl.col("string_value").str.split(".").list.last().eq("final").any().alias("is_final"),
        )
        return (
            self.records(relation)
            .join(flags, left_on="record_id", right_on="parent_id", how="left")
            .with_columns(
                pl.col(
                    "is_classmethod",
                    "is_setter",
                    "is_promised",
                    "is_read_as_data",
                    "is_final",
                ).fill_null(False)
            )
        )

    def paired_members(self) -> pl.LazyFrame:
        """Return inherited members beside declarations that answer the same name."""
        inherited = self.members("inherited").select(
            "fact_id",
            pl.col("record_id").alias("inherited_id"),
            "name",
            pl.col("parameters.present").alias("inherited_callable"),
            pl.col("asynchronous").alias("inherited_asynchronous"),
            pl.col("is_classmethod").alias("inherited_classmethod"),
            pl.col("is_promised").alias("inherited_promised"),
            pl.col("is_read_as_data").alias("inherited_read_as_data"),
            pl.col("is_final").alias("inherited_final"),
        )
        declared = self.members("declared").select(
            "fact_id",
            pl.col("record_id").alias("declared_id"),
            "name",
            pl.col("parameters.present").alias("declared_callable"),
            pl.col("asynchronous").alias("declared_asynchronous"),
            pl.col("is_classmethod").alias("declared_classmethod"),
            pl.col("is_setter").alias("declared_setter"),
            pl.col("is_promised").alias("declared_promised"),
            pl.col("is_read_as_data").alias("declared_read_as_data"),
        )
        return inherited.join(declared, on=["fact_id", "name"], how="inner")


def count_query(frame: pl.LazyFrame, measurement: str) -> CountQuery:
    """Return the standard precise count query for an override relation."""
    value = pl.col("value")
    return RuleQuery.integer(
        frame,
        value,
        findings=FindingQuery.precise_integer(
            frame,
            value,
            measurement,
            evidence=pl.col("evidence"),
        ),
    )


def occurrence_query(frame: pl.LazyFrame, measurement: str) -> OccurrenceQuery:
    """Return the standard precise occurrence query for an override relation."""
    value = pl.col("value")
    return RuleQuery.boolean(
        frame,
        value,
        findings=FindingQuery.precise_boolean(
            frame,
            value,
            measurement,
            evidence=pl.col("evidence"),
        ),
    )
