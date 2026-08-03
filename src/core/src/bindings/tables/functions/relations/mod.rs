use super::identity::entity_id;
use crate::bindings::frames::evidence_relation;
use crate::bindings::rows::parameter::ParameterRow;
use crate::functions::{ControlIncrement, FunctionParameter, FunctionRecord};
use crate::protocol::Node;
use polars::prelude::*;

pub(super) fn parameter_frame(records: &[FunctionRecord]) -> PolarsResult<DataFrame> {
    let rows = parameter_rows(records);
    df![
        "function_id" => rows.iter().map(|row| row.function_id).collect::<Vec<_>>(),
        "ordinal" => rows.iter().map(|row| row.ordinal).collect::<Vec<_>>(),
        "name" => rows.iter().map(|row| row.parameter.name.clone()).collect::<Vec<_>>(),
        "type_name" => rows.iter().map(|row| row.parameter.type_name.clone()).collect::<Vec<_>>(),
        "is_positional_only" => rows.iter().map(|row| row.parameter.contract.is_positional_only).collect::<Vec<_>>(),
        "is_keyword_only" => rows.iter().map(|row| row.parameter.contract.is_keyword_only).collect::<Vec<_>>(),
        "is_receiver" => rows.iter().map(|row| row.parameter.contract.is_receiver).collect::<Vec<_>>(),
        "is_required_by_external_contract" => rows.iter().map(|row| row.parameter.contract.is_required_by_external_contract).collect::<Vec<_>>(),
        "has_boolean_annotation" => rows.iter().map(|row| row.parameter.contract.has_boolean_annotation).collect::<Vec<_>>(),
        "has_boolean_default" => rows.iter().map(|row| row.parameter.contract.has_boolean_default).collect::<Vec<_>>(),
    ]
}

fn parameter_rows(records: &[FunctionRecord]) -> Vec<ParameterRow<'_, FunctionParameter>> {
    records
        .iter()
        .flat_map(|record| {
            let function_id = entity_id(record);
            record
                .structure
                .parameters
                .iter()
                .enumerate()
                .map(move |(ordinal, parameter)| ParameterRow {
                    function_id,
                    ordinal: ordinal as u64,
                    parameter,
                })
        })
        .collect()
}

pub(super) fn control_frame(records: &[FunctionRecord]) -> PolarsResult<DataFrame> {
    let rows = control_rows(records);
    df![
        "function_id" => rows.iter().map(|row| row.0).collect::<Vec<_>>(),
        "ordinal" => rows.iter().map(|row| row.1).collect::<Vec<_>>(),
        "kind" => rows.iter().map(|row| row.2.kind.as_str()).collect::<Vec<_>>(),
        "nesting_depth" => rows.iter().map(|row| row.2.nesting_depth as u64).collect::<Vec<_>>(),
    ]
}

fn control_rows(records: &[FunctionRecord]) -> Vec<(&str, u64, &ControlIncrement)> {
    records
        .iter()
        .flat_map(|record| {
            let function_id = entity_id(record);
            record
                .structure
                .control_increments
                .iter()
                .enumerate()
                .map(move |(ordinal, increment)| (function_id, ordinal as u64, increment))
        })
        .collect()
}

pub(super) fn decorator_frame(records: &[FunctionRecord]) -> PolarsResult<DataFrame> {
    function_string_relation(records, "decorator", |record| &record.structure.decorators)
}

fn function_string_relation(
    records: &[FunctionRecord],
    value_column: &str,
    values: for<'a> fn(&'a FunctionRecord) -> &'a [String],
) -> PolarsResult<DataFrame> {
    let rows = records
        .iter()
        .flat_map(|record| {
            let function_id = entity_id(record);
            values(record)
                .iter()
                .enumerate()
                .map(move |(ordinal, value)| (function_id, ordinal as u64, value.as_str()))
        })
        .collect::<Vec<_>>();
    df![
        "function_id" => rows.iter().map(|row| row.0).collect::<Vec<_>>(),
        "ordinal" => rows.iter().map(|row| row.1).collect::<Vec<_>>(),
        value_column => rows.iter().map(|row| row.2).collect::<Vec<_>>(),
    ]
}

pub(super) fn reference_frame(records: &[FunctionRecord]) -> PolarsResult<DataFrame> {
    let rows = reference_rows(records);
    df![
        "function_id" => rows.iter().map(|row| row.0).collect::<Vec<_>>(),
        "ordinal" => rows.iter().map(|row| row.1).collect::<Vec<_>>(),
        "node_id" => rows.iter().map(|row| row.2.id.clone()).collect::<Vec<_>>(),
        "path" => rows.iter().map(|row| row.2.span.path.clone()).collect::<Vec<_>>(),
        "start_line" => rows.iter().map(|row| row.2.span.start_line as u64).collect::<Vec<_>>(),
        "start_column" => rows.iter().map(|row| row.2.span.start_column as u64).collect::<Vec<_>>(),
        "end_line" => rows.iter().map(|row| row.2.span.end_line as u64).collect::<Vec<_>>(),
        "end_column" => rows.iter().map(|row| row.2.span.end_column as u64).collect::<Vec<_>>(),
        "kind" => rows.iter().map(|row| row.2.kind.clone()).collect::<Vec<_>>(),
        "text" => rows.iter().map(|row| row.2.text.clone()).collect::<Vec<_>>(),
    ]
}

fn reference_rows(records: &[FunctionRecord]) -> Vec<(&str, u64, &Node)> {
    records
        .iter()
        .flat_map(|record| {
            let function_id = entity_id(record);
            record
                .presentation
                .nodes
                .references
                .iter()
                .enumerate()
                .map(move |(ordinal, reference)| (function_id, ordinal as u64, reference))
        })
        .collect()
}

pub(super) fn tensor_role_frame(records: &[FunctionRecord]) -> PolarsResult<DataFrame> {
    function_string_relation(records, "role", |record| {
        &record.structure.recognized_tensor_roles
    })
}

pub(super) fn function_evidence_frame(records: &[FunctionRecord]) -> PolarsResult<DataFrame> {
    evidence_relation(records, "function_id", entity_id, |record| {
        &record.identity.evidence
    })
}
