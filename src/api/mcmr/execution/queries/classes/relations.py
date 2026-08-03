from typing import TYPE_CHECKING

import polars as pl

from ....table import ClassRelation
from ..generic.relations import CandidateRelations

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ....facts.foundation import Fact
    from ....table import Table


class ClassCandidateRelations(CandidateRelations):
    """Reconstruct contextual ClassFact payloads from specialized relations."""

    @classmethod
    def classes[Family: Fact](cls, table: Table[Family]) -> CandidateRelations:
        """Build one contextual candidate per class rather than per containing module."""
        entries = cls._class_entry_records(table)
        identity = cls._class_identity(table)
        facts = cls._candidate_facts(table, entries=entries, identity=identity)
        records = cls._candidate_records(table, identity)
        values = cls._candidate_values(table, identity)
        return cls(facts=facts, records=records, values=values)

    @classmethod
    def _candidate_facts[Family: Fact](
        cls,
        table: Table[Family],
        *,
        entries: pl.LazyFrame,
        identity: pl.LazyFrame,
    ) -> pl.LazyFrame:
        """Promote each nested class record into one candidate identity row."""
        module_facts = table.lazy(ClassRelation.FACTS).select(
            pl.col("fact_id").alias("module_fact_id"),
            "language",
            "has_approved_model_foundation_policy",
        )
        return (
            entries.join(
                identity.select("class_id", "generic_class_id"),
                left_on="record_id",
                right_on="generic_class_id",
                how="inner",
            )
            .join(
                module_facts,
                left_on="fact_id",
                right_on="module_fact_id",
                how="inner",
            )
            .select(
                "fact_order",
                pl.col("class_id").alias("fact_id"),
                pl.col("span.path").alias("path"),
                pl.col("span.start_line").cast(pl.UInt64).alias("start_line"),
                pl.col("span.start_column").cast(pl.UInt64).alias("start_column"),
                pl.col("span.end_line").cast(pl.UInt64).alias("end_line"),
                pl.col("span.end_column").cast(pl.UInt64).alias("end_column"),
                "language",
                "name",
                "is_test",
                "scope",
                "source",
                "visibility",
                "base_is_removable_overlap",
                "class_keywords.length",
                "decorators.length",
                "descendant_count",
                "direct_bases.length",
                "direct_subclasses.length",
                "directly_inherits_pydantic_base_model",
                "duplicate_component_alias_count",
                "field_count",
                "has_explicit_registry_name",
                "has_instance_fields",
                "has_noncooperative_concrete_collision",
                "has_ordinary_behavior",
                "has_redundant_direct_base",
                "importing_modules.length",
                "inherits_approved_model_foundation",
                "is_dataclass",
                "is_declarative_model",
                "is_exported",
                "is_instantiated",
                "is_pass_through_layer",
                "is_protocol",
                "methods.length",
                "only_cross_module_reference_is_subclass",
                "proposed_model_destination",
                "has_approved_model_foundation_policy",
            )
        )

    @classmethod
    def _candidate_records[Family: Fact](
        cls,
        table: Table[Family],
        identity: pl.LazyFrame,
    ) -> pl.LazyFrame:
        """Retarget method and evidence records from modules to class candidates."""
        class_map = identity.select("class_id", "generic_class_id")
        method_records = (
            cls._class_method_records(table)
            .join(class_map, left_on="parent_id", right_on="generic_class_id", how="inner")
            .drop("fact_id")
            .rename({"class_id": "fact_id"})
            .with_columns(
                pl.lit("methods").alias("relation"),
                pl.col("fact_id").alias("parent_id"),
                pl.lit(None, dtype=pl.Float64).alias("confidence"),
                pl.lit(None, dtype=pl.String).alias("detail"),
                pl.lit(None, dtype=pl.String).alias("signal"),
            )
        )
        evidence_records = (
            cls._class_evidence_records(table)
            .join(
                identity.select("class_id", pl.col("fact_id").alias("module_fact_id")),
                left_on="fact_id",
                right_on="module_fact_id",
                how="inner",
            )
            .drop("fact_id")
            .rename({"class_id": "fact_id"})
            .with_columns(pl.col("fact_id").alias("parent_id"))
        )
        return pl.concat([method_records, evidence_records], how="diagonal_relaxed")

    @classmethod
    def _candidate_values[Family: Fact](
        cls,
        table: Table[Family],
        identity: pl.LazyFrame,
    ) -> pl.LazyFrame:
        """Retarget class and method scalar values to their class candidates."""
        class_map = identity.select("class_id", "generic_class_id")
        values = cls._class_values(table)
        class_values = (
            values.join(class_map, left_on="parent_id", right_on="generic_class_id", how="inner")
            .drop("fact_id")
            .rename({"class_id": "fact_id"})
        )
        method_map = cls._method_identity(table).select("class_id", "generic_method_id")
        method_values = (
            values.join(
                method_map,
                left_on="parent_id",
                right_on="generic_method_id",
                how="inner",
            )
            .drop("fact_id")
            .rename({"class_id": "fact_id"})
        )
        return pl.concat([class_values, method_values], how="vertical")

    @classmethod
    def _class_entry_records[Family: Fact](cls, table: Table[Family]) -> pl.LazyFrame:
        """Project each nested class into one universal record row."""
        classes = table.lazy(ClassRelation.CLASSES)
        direct_bases = table.lazy(ClassRelation.DIRECT_BASES)
        class_decorators = table.lazy(ClassRelation.CLASS_DECORATORS)
        class_keywords = table.lazy(ClassRelation.CLASS_KEYWORDS)
        direct_subclasses = table.lazy(ClassRelation.DIRECT_SUBCLASSES)
        importing_modules = table.lazy(ClassRelation.IMPORTING_MODULES)
        class_identity = cls._class_identity(table)
        return (
            classes.join(class_identity, on="class_id", how="inner")
            .join(
                cls.lengths(direct_bases, key="class_id", name="direct_bases.length"),
                on="class_id",
                how="left",
            )
            .join(
                cls.lengths(class_decorators, key="class_id", name="decorators.length"),
                on="class_id",
                how="left",
            )
            .join(
                cls.lengths(class_keywords, key="class_id", name="class_keywords.length"),
                on="class_id",
                how="left",
            )
            .join(
                cls.lengths(direct_subclasses, key="class_id", name="direct_subclasses.length"),
                on="class_id",
                how="left",
            )
            .join(
                cls.lengths(importing_modules, key="class_id", name="importing_modules.length"),
                on="class_id",
                how="left",
            )
            .with_columns(
                pl.col(
                    "direct_bases.length",
                    "decorators.length",
                    "class_keywords.length",
                    "direct_subclasses.length",
                    "importing_modules.length",
                )
                .fill_null(0)
                .cast(pl.Int64)
            )
            .select(
                "fact_order",
                "fact_id",
                pl.lit("classes").alias("relation"),
                pl.col("fact_id").alias("parent_id"),
                pl.col("generic_class_id").alias("record_id"),
                "ordinal",
                "base_is_removable_overlap",
                "class_keywords.length",
                pl.lit(True).alias("class_keywords.present"),
                "decorators.length",
                pl.lit(True).alias("decorators.present"),
                pl.col("descendant_count").cast(pl.Int64),
                "direct_bases.length",
                pl.lit(True).alias("direct_bases.present"),
                pl.col("direct_subclasses.length").cast(pl.Int64),
                pl.lit(True).alias("direct_subclasses.present"),
                "directly_inherits_pydantic_base_model",
                pl.col("duplicate_component_alias_count").cast(pl.Int64),
                pl.col("field_count").cast(pl.Int64),
                "has_explicit_registry_name",
                "has_instance_fields",
                "has_noncooperative_concrete_collision",
                "has_ordinary_behavior",
                "has_redundant_direct_base",
                "importing_modules.length",
                pl.lit(True).alias("importing_modules.present"),
                "inherits_approved_model_foundation",
                "is_dataclass",
                "is_declarative_model",
                "is_exported",
                "is_instantiated",
                "is_test",
                "is_pass_through_layer",
                "is_protocol",
                "name",
                "only_cross_module_reference_is_subclass",
                "proposed_model_destination",
                "source",
                "scope",
                *cls.span_columns(source="", target="span"),
                "path",
                "visibility",
                pl.col("method_count").cast(pl.Int64).alias("methods.length"),
                pl.lit(True).alias("methods.present"),
                pl.lit(0).alias("candidate_order_0"),
                pl.col("class_order").alias("candidate_order_1"),
                pl.col("method_count").alias("candidate_order_2"),
                pl.lit(1).alias("candidate_order_3"),
            )
        )

    @classmethod
    def _class_evidence_records[Family: Fact](cls, table: Table[Family]) -> pl.LazyFrame:
        """Project each ClassFact evidence item into one universal record row."""
        evidence = table.lazy(ClassRelation.EVIDENCE)
        fact_identity = table.lazy(ClassRelation.FACTS).select("fact_order", "fact_id")
        return evidence.join(fact_identity, on="fact_id", how="inner").select(
            "fact_order",
            "fact_id",
            pl.lit("evidence").alias("relation"),
            pl.col("fact_id").alias("parent_id"),
            pl.concat_str("fact_id", pl.lit("/evidence:"), pl.col("ordinal")).alias("record_id"),
            "ordinal",
            "confidence",
            "detail",
            "signal",
            "source",
            pl.lit(2).alias("candidate_order_0"),
            pl.col("ordinal").alias("candidate_order_1"),
            pl.lit(0).alias("candidate_order_2"),
            pl.lit(0).alias("candidate_order_3"),
        )

    @classmethod
    def _class_identity[Family: Fact](cls, table: Table[Family]) -> pl.LazyFrame:
        """Map specialized class IDs to stable generic record identities."""
        fact_identity = table.lazy(ClassRelation.FACTS).select("fact_order", "fact_id")
        classes = table.lazy(ClassRelation.CLASSES)
        methods = table.lazy(ClassRelation.METHODS)
        return (
            classes.join(fact_identity, on="fact_id", how="inner")
            .join(
                cls.lengths(methods, key="class_id", name="method_count"),
                on="class_id",
                how="left",
            )
            .with_columns(
                pl.col("method_count").fill_null(0).cast(pl.UInt64),
                pl.concat_str("fact_id", pl.lit("/classes:"), pl.col("ordinal")).alias(
                    "generic_class_id"
                ),
            )
            .select(
                "class_id",
                "fact_order",
                "fact_id",
                pl.col("ordinal").alias("class_order"),
                "method_count",
                "generic_class_id",
            )
        )

    @classmethod
    def _class_method_records[Family: Fact](cls, table: Table[Family]) -> pl.LazyFrame:
        """Project each nested method into one universal record row."""
        methods = table.lazy(ClassRelation.METHODS)
        method_decorators = table.lazy(ClassRelation.METHOD_DECORATORS)
        owner_calls = table.lazy(ClassRelation.OWNER_QUALIFIED_CALLS)
        method_identity = cls._method_identity(table)
        return (
            methods.join(method_identity, on="method_id", how="inner")
            .join(
                cls.lengths(method_decorators, key="method_id", name="decorators.length"),
                on="method_id",
                how="left",
            )
            .join(
                cls.lengths(owner_calls, key="method_id", name="owner_qualified_calls.length"),
                on="method_id",
                how="left",
            )
            .with_columns(
                pl.col("decorators.length", "owner_qualified_calls.length")
                .fill_null(0)
                .cast(pl.Int64)
            )
            .select(
                "fact_order",
                "fact_id",
                pl.lit("classes.methods").alias("relation"),
                pl.col("generic_class_id").alias("parent_id"),
                pl.col("generic_method_id").alias("record_id"),
                "ordinal",
                "decorators.length",
                pl.lit(True).alias("decorators.present"),
                "is_protocol_name",
                "kind",
                "name",
                "owner_qualified_calls.length",
                pl.lit(True).alias("owner_qualified_calls.present"),
                pl.col("region").cast(pl.Int64),
                "reads_receiver",
                "reads_receiver_state",
                "source",
                *cls.span_columns(source="", target="span"),
                "visibility",
                pl.lit(0).alias("candidate_order_0"),
                pl.col("class_order").alias("candidate_order_1"),
                pl.col("method_order").alias("candidate_order_2"),
                pl.lit(0).alias("candidate_order_3"),
            )
        )

    @classmethod
    def _class_value_rows(
        cls,
        identity: pl.LazyFrame,
        sources: Sequence[tuple[str, pl.LazyFrame, int]],
    ) -> list[pl.LazyFrame]:
        """Project class-owned string collections into universal value rows."""
        values: list[pl.LazyFrame] = []
        for relation, source, order in sources:
            selected = source.join(identity, on="class_id", how="inner").select(
                "fact_order",
                "fact_id",
                pl.col("generic_class_id").alias("parent_id"),
                "ordinal",
                "value",
                pl.lit(0).alias("candidate_order_0"),
                pl.col("class_order").alias("candidate_order_1"),
                pl.lit(order).alias("candidate_order_2"),
                pl.lit(0).alias("candidate_order_3"),
            )
            values.append(cls.value_rows(selected, relation))
        return values

    @classmethod
    def _class_values[Family: Fact](cls, table: Table[Family]) -> pl.LazyFrame:
        """Project all ClassFact string collections into universal value rows."""
        class_values = cls._class_value_rows(
            cls._class_identity(table),
            (
                ("classes.class_keywords", table.lazy(ClassRelation.CLASS_KEYWORDS), 0),
                ("classes.decorators", table.lazy(ClassRelation.CLASS_DECORATORS), 1),
                ("classes.direct_bases", table.lazy(ClassRelation.DIRECT_BASES), 2),
                ("classes.direct_subclasses", table.lazy(ClassRelation.DIRECT_SUBCLASSES), 3),
                ("classes.importing_modules", table.lazy(ClassRelation.IMPORTING_MODULES), 4),
            ),
        )
        method_values = cls._method_value_rows(
            cls._method_identity(table),
            (
                ("classes.methods.decorators", table.lazy(ClassRelation.METHOD_DECORATORS), 0),
                (
                    "classes.methods.owner_qualified_calls",
                    table.lazy(ClassRelation.OWNER_QUALIFIED_CALLS),
                    1,
                ),
            ),
        )
        return pl.concat([*class_values, *method_values], how="vertical")

    @classmethod
    def _method_identity[Family: Fact](cls, table: Table[Family]) -> pl.LazyFrame:
        """Map specialized method IDs to stable nested generic record identities."""
        methods = table.lazy(ClassRelation.METHODS)
        return (
            methods.join(cls._class_identity(table), on="class_id", how="inner")
            .with_columns(
                pl.concat_str(
                    "generic_class_id", pl.lit("/classes.methods:"), pl.col("ordinal")
                ).alias("generic_method_id")
            )
            .select(
                "method_id",
                "class_id",
                "fact_order",
                "fact_id",
                "class_order",
                pl.col("ordinal").alias("method_order"),
                "generic_class_id",
                "generic_method_id",
            )
        )

    @classmethod
    def _method_value_rows(
        cls,
        identity: pl.LazyFrame,
        sources: Sequence[tuple[str, pl.LazyFrame, int]],
    ) -> list[pl.LazyFrame]:
        """Project method-owned string collections into universal value rows."""
        values: list[pl.LazyFrame] = []
        for relation, source, order in sources:
            selected = source.join(identity, on="method_id", how="inner").select(
                "fact_order",
                "fact_id",
                pl.col("generic_method_id").alias("parent_id"),
                "ordinal",
                "value",
                pl.lit(0).alias("candidate_order_0"),
                pl.col("class_order").alias("candidate_order_1"),
                pl.lit(5).alias("candidate_order_2"),
                (pl.col("method_order") * 2 + order).alias("candidate_order_3"),
            )
            values.append(cls.value_rows(selected, relation))
        return values
