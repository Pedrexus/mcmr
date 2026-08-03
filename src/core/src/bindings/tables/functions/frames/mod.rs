use super::identity::entity_id;
use crate::bindings::frames::combined_frame;
use crate::bindings::frames::located::fact_columns;
use crate::functions::FunctionRecord;
use polars::prelude::*;

pub(super) fn function_frame(records: &[FunctionRecord]) -> PolarsResult<DataFrame> {
    let mut columns = fact_columns(records)?;
    for frame in [
        function_text_frame(records)?,
        function_definition_frame(records)?,
        function_body_expression_frame(records)?,
        function_measure_frame(records)?,
        function_flag_frame(records)?,
    ] {
        columns.extend(frame.into_columns());
    }
    DataFrame::new(records.len(), columns)
}

fn function_text_frame(records: &[FunctionRecord]) -> PolarsResult<DataFrame> {
    df![
        "entity_id" => records.iter().map(entity_id).collect::<Vec<_>>(),
        "fact_key" => records.iter().map(|row| row.identity.key.as_str()).collect::<Vec<_>>(),
        "name" => records.iter().map(|row| row.identity.name.as_str()).collect::<Vec<_>>(),
        "scope" => records.iter().map(|row| row.identity.scope.as_str()).collect::<Vec<_>>(),
        "visibility" => records.iter().map(|row| row.presentation.visibility.as_str()).collect::<Vec<_>>(),
        "cache_decorator" => records.iter().map(|row| row.presentation.cache_decorator.as_str()).collect::<Vec<_>>(),
        "docstring" => records.iter().map(|row| row.presentation.docstring.as_str()).collect::<Vec<_>>(),
        "sole_reference_owner_class" => records.iter().map(|row| row.presentation.sole_reference_owner_class.as_str()).collect::<Vec<_>>(),
        "sole_reference_owner_definition_id" => records.iter().map(|row| row.presentation.nodes.sole_reference_owner_definition.as_ref().map(|node| node.id.as_str())).collect::<Vec<_>>(),
        "sole_reference_owner_definition_path" => records.iter().map(|row| row.presentation.nodes.sole_reference_owner_definition.as_ref().map(|node| node.span.path.as_str())).collect::<Vec<_>>(),
        "sole_reference_owner_definition_start_line" => records.iter().map(|row| row.presentation.nodes.sole_reference_owner_definition.as_ref().map(|node| node.span.start_line as u64)).collect::<Vec<_>>(),
        "sole_reference_owner_definition_start_column" => records.iter().map(|row| row.presentation.nodes.sole_reference_owner_definition.as_ref().map(|node| node.span.start_column as u64)).collect::<Vec<_>>(),
        "sole_reference_owner_definition_end_line" => records.iter().map(|row| row.presentation.nodes.sole_reference_owner_definition.as_ref().map(|node| node.span.end_line as u64)).collect::<Vec<_>>(),
        "sole_reference_owner_definition_end_column" => records.iter().map(|row| row.presentation.nodes.sole_reference_owner_definition.as_ref().map(|node| node.span.end_column as u64)).collect::<Vec<_>>(),
        "sole_reference_owner_definition_kind" => records.iter().map(|row| row.presentation.nodes.sole_reference_owner_definition.as_ref().map(|node| node.kind.as_str())).collect::<Vec<_>>(),
        "sole_reference_owner_definition_text" => records.iter().map(|row| row.presentation.nodes.sole_reference_owner_definition.as_ref().map(|node| node.text.as_str())).collect::<Vec<_>>(),
    ]
}

fn function_definition_frame(records: &[FunctionRecord]) -> PolarsResult<DataFrame> {
    df![
        "definition_id" => records.iter().map(|row| row.presentation.nodes.definition.as_ref().map(|node| node.id.as_str())).collect::<Vec<_>>(),
        "definition_path" => records.iter().map(|row| row.presentation.nodes.definition.as_ref().map(|node| node.span.path.as_str())).collect::<Vec<_>>(),
        "definition_start_line" => records.iter().map(|row| row.presentation.nodes.definition.as_ref().map(|node| node.span.start_line as u64)).collect::<Vec<_>>(),
        "definition_start_column" => records.iter().map(|row| row.presentation.nodes.definition.as_ref().map(|node| node.span.start_column as u64)).collect::<Vec<_>>(),
        "definition_end_line" => records.iter().map(|row| row.presentation.nodes.definition.as_ref().map(|node| node.span.end_line as u64)).collect::<Vec<_>>(),
        "definition_end_column" => records.iter().map(|row| row.presentation.nodes.definition.as_ref().map(|node| node.span.end_column as u64)).collect::<Vec<_>>(),
        "definition_kind" => records.iter().map(|row| row.presentation.nodes.definition.as_ref().map(|node| node.kind.as_str())).collect::<Vec<_>>(),
        "definition_text" => records.iter().map(|row| row.presentation.nodes.definition.as_ref().map(|node| node.text.as_str())).collect::<Vec<_>>(),
    ]
}

fn function_body_expression_frame(records: &[FunctionRecord]) -> PolarsResult<DataFrame> {
    df![
        "body_expression_id" => records.iter().map(|row| row.presentation.nodes.body_expression.as_ref().map(|node| node.id.as_str())).collect::<Vec<_>>(),
        "body_expression_path" => records.iter().map(|row| row.presentation.nodes.body_expression.as_ref().map(|node| node.span.path.as_str())).collect::<Vec<_>>(),
        "body_expression_start_line" => records.iter().map(|row| row.presentation.nodes.body_expression.as_ref().map(|node| node.span.start_line as u64)).collect::<Vec<_>>(),
        "body_expression_start_column" => records.iter().map(|row| row.presentation.nodes.body_expression.as_ref().map(|node| node.span.start_column as u64)).collect::<Vec<_>>(),
        "body_expression_end_line" => records.iter().map(|row| row.presentation.nodes.body_expression.as_ref().map(|node| node.span.end_line as u64)).collect::<Vec<_>>(),
        "body_expression_end_column" => records.iter().map(|row| row.presentation.nodes.body_expression.as_ref().map(|node| node.span.end_column as u64)).collect::<Vec<_>>(),
        "body_expression_kind" => records.iter().map(|row| row.presentation.nodes.body_expression.as_ref().map(|node| node.kind.as_str())).collect::<Vec<_>>(),
        "body_expression_text" => records.iter().map(|row| row.presentation.nodes.body_expression.as_ref().map(|node| node.text.as_str())).collect::<Vec<_>>(),
    ]
}

fn function_measure_frame(records: &[FunctionRecord]) -> PolarsResult<DataFrame> {
    df![
        "created_task_count" => records.iter().map(|row| row.structure.created_task_count as u64).collect::<Vec<_>>(),
        "implementation_lines" => records.iter().map(|row| row.structure.implementation_lines as u64).collect::<Vec<_>>(),
        "direct_statement_count" => records.iter().map(|row| row.structure.direct_statement_count as u64).collect::<Vec<_>>(),
        "reference_count" => records.iter().map(|row| row.measures.reference_count as u64).collect::<Vec<_>>(),
        "behavior_operation_count" => records.iter().map(|row| row.measures.behavior_operation_count as u64).collect::<Vec<_>>(),
        "conditional_count" => records.iter().map(|row| row.measures.conditional_count as u64).collect::<Vec<_>>(),
    ]
}

fn function_flag_frame(records: &[FunctionRecord]) -> PolarsResult<DataFrame> {
    combined_frame(
        records.len(),
        [
            function_async_flag_frame(records)?,
            function_contract_flag_frame(records)?,
            function_pattern_flag_frame(records)?,
        ],
    )
}

fn function_async_flag_frame(records: &[FunctionRecord]) -> PolarsResult<DataFrame> {
    df![
        "is_test" => records.iter().map(|row| row.identity.is_test).collect::<Vec<_>>(),
        "gather_consumes_created_tasks" => records.iter().map(|row| row.measures.gather_consumes_created_tasks).collect::<Vec<_>>(),
        "gather_returns_exceptions" => records.iter().map(|row| row.measures.gather_returns_exceptions).collect::<Vec<_>>(),
        "has_task_group" => records.iter().map(|row| row.measures.has_task_group).collect::<Vec<_>>(),
        "reads_receiver" => records.iter().map(|row| row.measures.reads_receiver).collect::<Vec<_>>(),
        "has_tensor_shape_semantics" => records.iter().map(|row| row.semantics.roles.has_tensor_shape_semantics).collect::<Vec<_>>(),
        "has_tensor_dtype_semantics" => records.iter().map(|row| row.semantics.roles.has_tensor_dtype_semantics).collect::<Vec<_>>(),
        "is_protocol_name" => records.iter().map(|row| row.semantics.roles.is_protocol_name).collect::<Vec<_>>(),
        "is_async" => records.iter().map(|row| row.semantics.roles.is_async).collect::<Vec<_>>(),
    ]
}

fn function_contract_flag_frame(records: &[FunctionRecord]) -> PolarsResult<DataFrame> {
    df![
        "is_recursive" => records.iter().map(|row| row.semantics.roles.is_recursive).collect::<Vec<_>>(),
        "is_first_class_reference" => records.iter().map(|row| row.semantics.roles.is_first_class_reference).collect::<Vec<_>>(),
        "is_abstract" => records.iter().map(|row| row.semantics.roles.is_abstract).collect::<Vec<_>>(),
        "is_protocol_member" => records.iter().map(|row| row.semantics.outcomes.is_protocol_member).collect::<Vec<_>>(),
        "is_overload" => records.iter().map(|row| row.semantics.outcomes.is_overload).collect::<Vec<_>>(),
        "is_property" => records.iter().map(|row| row.semantics.outcomes.is_property).collect::<Vec<_>>(),
        "is_framework_hook" => records.iter().map(|row| row.semantics.outcomes.is_framework_hook).collect::<Vec<_>>(),
        "is_declarative_body" => records.iter().map(|row| row.semantics.outcomes.is_declarative_body).collect::<Vec<_>>(),
        "is_polymorphic" => records.iter().map(|row| row.semantics.outcomes.is_polymorphic).collect::<Vec<_>>(),
        "is_pass_body" => records.iter().map(|row| row.semantics.outcomes.is_pass_body).collect::<Vec<_>>(),
        "is_raise_body" => records.iter().map(|row| row.validation.output.is_raise_body).collect::<Vec<_>>(),
    ]
}

fn function_pattern_flag_frame(records: &[FunctionRecord]) -> PolarsResult<DataFrame> {
    df![
        "returns_single_call" => records.iter().map(|row| row.validation.output.returns_single_call).collect::<Vec<_>>(),
        "forwards_only_parameter_unchanged" => records.iter().map(|row| row.validation.output.forwards_only_parameter_unchanged).collect::<Vec<_>>(),
        "is_model_method" => records.iter().map(|row| row.validation.input.is_model_method).collect::<Vec<_>>(),
        "is_pydantic_validator" => records.iter().map(|row| row.validation.input.is_pydantic_validator).collect::<Vec<_>>(),
        "checks_raw_input_type" => records.iter().map(|row| row.validation.input.checks_raw_input_type).collect::<Vec<_>>(),
        "raises_validation_exception" => records.iter().map(|row| row.validation.input.raises_validation_exception).collect::<Vec<_>>(),
        "constructs_owner_model" => records.iter().map(|row| row.validation.output.constructs_owner_model).collect::<Vec<_>>(),
    ]
}
