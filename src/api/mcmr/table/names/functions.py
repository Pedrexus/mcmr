from enum import StrEnum, auto
from typing import TYPE_CHECKING

import polars as pl

from ..runtime.candidates import CandidateRelations

if TYPE_CHECKING:
    from ...facts.foundation import Fact
    from ..runtime.table import Table


class FunctionRelation(StrEnum):
    """Reconstruct contextual FunctionFact payloads from specialized relations."""

    FUNCTIONS = auto()
    PARAMETERS = auto()
    CONTROLS = auto()
    DECORATORS = auto()
    REFERENCES = auto()
    TENSOR_ROLES = auto()
    EVIDENCE = auto()

    @staticmethod
    def function_record_columns() -> tuple[str, ...]:
        """Return the universal FunctionFact record schema in stable payload order."""
        return (
            "fact_order",
            "fact_id",
            "relation",
            "parent_id",
            "record_id",
            "ordinal",
            "confidence",
            "detail",
            "has_boolean_annotation",
            "has_boolean_default",
            "id",
            "is_keyword_only",
            "is_positional_only",
            "is_receiver",
            "is_required_by_external_contract",
            "kind",
            "name",
            "nesting_depth",
            "signal",
            "source",
            "span.end_column",
            "span.end_line",
            "span.path",
            "span.start_column",
            "span.start_line",
            "text",
            "type_name",
            "candidate_order_0",
            "candidate_order_1",
            "candidate_order_2",
            "candidate_order_3",
        )

    @classmethod
    def candidates[Family: Fact](cls, table: Table[Family]) -> pl.LazyFrame:
        """Reproduce the FunctionFact model payload from its specialized native frames."""
        return CandidateRelations(
            facts=cls.function_facts(table),
            records=cls.function_records(table),
            values=cls.function_values(table),
        ).candidates()

    @classmethod
    def function_facts[Family: Fact](cls, table: Table[Family]) -> pl.LazyFrame:
        """Project FunctionFact scalar fields and normalized child lengths."""
        functions = table.lazy(FunctionRelation.FUNCTIONS)
        parameters = table.lazy(FunctionRelation.PARAMETERS)
        controls = table.lazy(FunctionRelation.CONTROLS)
        decorators = table.lazy(FunctionRelation.DECORATORS)
        references = table.lazy(FunctionRelation.REFERENCES)
        tensor_roles = table.lazy(FunctionRelation.TENSOR_ROLES)
        evidence = table.lazy(FunctionRelation.EVIDENCE)
        return (
            functions.join(
                CandidateRelations.lengths(
                    controls, key="function_id", name="control_increments.length"
                ),
                left_on="entity_id",
                right_on="function_id",
                how="left",
            )
            .join(
                CandidateRelations.lengths(
                    decorators, key="function_id", name="decorators.length"
                ),
                left_on="entity_id",
                right_on="function_id",
                how="left",
            )
            .join(
                CandidateRelations.lengths(evidence, key="function_id", name="evidence.length"),
                left_on="entity_id",
                right_on="function_id",
                how="left",
            )
            .join(
                CandidateRelations.lengths(
                    parameters, key="function_id", name="parameters.length"
                ),
                left_on="entity_id",
                right_on="function_id",
                how="left",
            )
            .join(
                CandidateRelations.lengths(
                    tensor_roles, key="function_id", name="recognized_tensor_roles.length"
                ),
                left_on="entity_id",
                right_on="function_id",
                how="left",
            )
            .join(
                CandidateRelations.lengths(
                    references, key="function_id", name="references.length"
                ),
                left_on="entity_id",
                right_on="function_id",
                how="left",
            )
            .with_columns(
                pl.col(
                    "control_increments.length",
                    "decorators.length",
                    "evidence.length",
                    "parameters.length",
                    "recognized_tensor_roles.length",
                    "references.length",
                )
                .fill_null(0)
                .cast(pl.Int64),
            )
            .select(
                "fact_order",
                "fact_id",
                "path",
                "start_line",
                "start_column",
                "end_line",
                "end_column",
                "language",
                pl.col("behavior_operation_count").cast(pl.Int64),
                pl.col("body_expression_id").alias("body_expression.id"),
                pl.col("body_expression_kind").alias("body_expression.kind"),
                *CandidateRelations.span_columns(
                    source="body_expression_", target="body_expression.span"
                ),
                pl.col("body_expression_text").alias("body_expression.text"),
                "cache_decorator",
                "checks_raw_input_type",
                pl.col("conditional_count").cast(pl.Int64),
                "constructs_owner_model",
                "control_increments.length",
                pl.lit(True).alias("control_increments.present"),
                pl.col("created_task_count").cast(pl.Int64),
                "decorators.length",
                pl.lit(True).alias("decorators.present"),
                pl.col("definition_id").alias("definition.id"),
                pl.col("definition_kind").alias("definition.kind"),
                *CandidateRelations.span_columns(source="definition_", target="definition.span"),
                pl.col("definition_text").alias("definition.text"),
                pl.col("direct_statement_count").cast(pl.Int64),
                "docstring",
                "evidence.length",
                pl.lit(True).alias("evidence.present"),
                "forwards_only_parameter_unchanged",
                "gather_consumes_created_tasks",
                "gather_returns_exceptions",
                "has_task_group",
                "has_tensor_dtype_semantics",
                "has_tensor_shape_semantics",
                pl.col("implementation_lines").cast(pl.Int64),
                "is_abstract",
                "is_async",
                "is_declarative_body",
                "is_first_class_reference",
                "is_framework_hook",
                "is_model_method",
                "is_overload",
                "is_pass_body",
                "is_polymorphic",
                "is_property",
                "is_protocol_member",
                "is_protocol_name",
                "is_pydantic_validator",
                "is_raise_body",
                "is_recursive",
                "is_test",
                "name",
                "parameters.length",
                pl.lit(True).alias("parameters.present"),
                "raises_validation_exception",
                "reads_receiver",
                "recognized_tensor_roles.length",
                pl.lit(True).alias("recognized_tensor_roles.present"),
                pl.col("reference_count").cast(pl.Int64),
                "references.length",
                pl.lit(True).alias("references.present"),
                "returns_single_call",
                "scope",
                "sole_reference_owner_class",
                pl.col("sole_reference_owner_definition_id").alias(
                    "sole_reference_owner_definition.id"
                ),
                pl.col("sole_reference_owner_definition_kind").alias(
                    "sole_reference_owner_definition.kind"
                ),
                *CandidateRelations.span_columns(
                    source="sole_reference_owner_definition_",
                    target="sole_reference_owner_definition.span",
                ),
                pl.col("sole_reference_owner_definition_text").alias(
                    "sole_reference_owner_definition.text"
                ),
                "visibility",
            )
        )

    @classmethod
    def function_records[Family: Fact](cls, table: Table[Family]) -> pl.LazyFrame:
        """Project FunctionFact structured children into universal record rows."""
        functions = table.lazy(FunctionRelation.FUNCTIONS)
        controls = table.lazy(FunctionRelation.CONTROLS)
        evidence = table.lazy(FunctionRelation.EVIDENCE)
        parameters = table.lazy(FunctionRelation.PARAMETERS)
        references = table.lazy(FunctionRelation.REFERENCES)
        identity = functions.select("entity_id", "fact_order", "fact_id")
        controls_records = controls.join(
            identity, left_on="function_id", right_on="entity_id", how="inner"
        ).select(
            "fact_order",
            "fact_id",
            pl.lit("control_increments").alias("relation"),
            pl.col("fact_id").alias("parent_id"),
            pl.concat_str("fact_id", pl.lit("/control_increments:"), pl.col("ordinal")).alias(
                "record_id"
            ),
            "ordinal",
            "kind",
            pl.col("nesting_depth").cast(pl.Int64),
            pl.lit(0).alias("candidate_order_0"),
            pl.lit(0).alias("candidate_order_1"),
            pl.lit(0).alias("candidate_order_2"),
            pl.lit(0).alias("candidate_order_3"),
        )
        evidence_records = evidence.join(
            identity, left_on="function_id", right_on="entity_id", how="inner"
        ).select(
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
            pl.lit(1).alias("candidate_order_0"),
            pl.lit(0).alias("candidate_order_1"),
            pl.lit(0).alias("candidate_order_2"),
            pl.lit(0).alias("candidate_order_3"),
        )
        parameter_records = parameters.join(
            identity, left_on="function_id", right_on="entity_id", how="inner"
        ).select(
            "fact_order",
            "fact_id",
            pl.lit("parameters").alias("relation"),
            pl.col("fact_id").alias("parent_id"),
            pl.concat_str("fact_id", pl.lit("/parameters:"), pl.col("ordinal")).alias("record_id"),
            "ordinal",
            "has_boolean_annotation",
            "has_boolean_default",
            "is_keyword_only",
            "is_positional_only",
            "is_receiver",
            "is_required_by_external_contract",
            "name",
            "type_name",
            pl.lit(2).alias("candidate_order_0"),
            pl.lit(0).alias("candidate_order_1"),
            pl.lit(0).alias("candidate_order_2"),
            pl.lit(0).alias("candidate_order_3"),
        )
        reference_records = references.join(
            identity, left_on="function_id", right_on="entity_id", how="inner"
        ).select(
            "fact_order",
            "fact_id",
            pl.lit("references").alias("relation"),
            pl.col("fact_id").alias("parent_id"),
            pl.concat_str("fact_id", pl.lit("/references:"), pl.col("ordinal")).alias("record_id"),
            "ordinal",
            pl.col("node_id").alias("id"),
            "kind",
            *CandidateRelations.span_columns(source="", target="span"),
            "text",
            pl.lit(3).alias("candidate_order_0"),
            pl.lit(0).alias("candidate_order_1"),
            pl.lit(0).alias("candidate_order_2"),
            pl.lit(0).alias("candidate_order_3"),
        )
        return pl.concat(
            [controls_records, evidence_records, parameter_records, reference_records],
            how="diagonal_relaxed",
        ).select(*cls.function_record_columns())

    @classmethod
    def function_values[Family: Fact](cls, table: Table[Family]) -> pl.LazyFrame:
        """Project FunctionFact string collections into universal value rows."""
        functions = table.lazy(FunctionRelation.FUNCTIONS)
        decorators = table.lazy(FunctionRelation.DECORATORS)
        tensor_roles = table.lazy(FunctionRelation.TENSOR_ROLES)
        identity = functions.select("entity_id", "fact_order", "fact_id")
        decorator_values = (
            decorators.join(identity, left_on="function_id", right_on="entity_id", how="inner")
            .with_columns(pl.len().over("function_id").alias("container_length"))
            .select(
                "fact_order",
                "fact_id",
                pl.col("fact_id").alias("parent_id"),
                "ordinal",
                "container_length",
                pl.col("decorator").alias("value"),
                pl.lit(0).alias("candidate_order_0"),
                pl.lit(0).alias("candidate_order_1"),
                pl.lit(0).alias("candidate_order_2"),
                pl.lit(0).alias("candidate_order_3"),
            )
        )
        tensor_values = (
            tensor_roles.join(identity, left_on="function_id", right_on="entity_id", how="inner")
            .with_columns(pl.len().over("function_id").alias("container_length"))
            .select(
                "fact_order",
                "fact_id",
                pl.col("fact_id").alias("parent_id"),
                "ordinal",
                "container_length",
                pl.col("role").alias("value"),
                pl.lit(1).alias("candidate_order_0"),
                pl.lit(0).alias("candidate_order_1"),
                pl.lit(0).alias("candidate_order_2"),
                pl.lit(0).alias("candidate_order_3"),
            )
        )
        return pl.concat(
            [
                CandidateRelations.value_rows(decorator_values, "decorators"),
                CandidateRelations.value_rows(tensor_values, "recognized_tensor_roles"),
            ],
            how="vertical",
        )
