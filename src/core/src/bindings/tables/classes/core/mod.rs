use crate::bindings::frames::combined_frame;
use crate::bindings::frames::evidence_relation;
use crate::bindings::frames::located::boolean_fact_frame;
use crate::bindings::frames::located::fact_key;
use crate::bindings::relations::{NestedRow, nested_rows};
use crate::bindings::rows::method::MethodRow;
use crate::classes::{ClassAnalysisRecord, ClassRecord, MethodRecord};
use polars::prelude::*;

pub(super) fn class_relation_rows<'record, Value>(
    records: &'record [ClassRecord],
    relation: &str,
    values: for<'value> fn(&'value ClassRecord) -> &'value [Value],
) -> Vec<NestedRow<'record, Value>> {
    nested_rows(records, relation, |record| record.key.as_str(), values)
}

pub(super) fn class_fact_frame(records: &[ClassRecord]) -> PolarsResult<DataFrame> {
    boolean_fact_frame(records, "has_approved_model_foundation_policy", |record| {
        record.has_approved_model_foundation_policy
    })
}

impl<'a> NestedRow<'a, ClassAnalysisRecord> {
    fn class(&self) -> &'a ClassAnalysisRecord {
        self.value
    }
}

pub(super) fn class_rows(records: &[ClassRecord]) -> Vec<NestedRow<'_, ClassAnalysisRecord>> {
    nested_rows(
        records,
        "class",
        |record| record.key.as_str(),
        |record| &record.classes,
    )
}

pub(super) fn class_frame(records: &[ClassRecord]) -> PolarsResult<DataFrame> {
    let rows = class_rows(records);
    combined_frame(
        rows.len(),
        [
            class_identity_frame(&rows)?,
            class_measure_frame(&rows)?,
            class_flag_frame(&rows)?,
        ],
    )
}

fn class_identity_frame(rows: &[NestedRow<'_, ClassAnalysisRecord>]) -> PolarsResult<DataFrame> {
    df![
        "class_id" => rows.iter().map(|row| row.id.clone()).collect::<Vec<_>>(),
        "fact_id" => rows.iter().map(|row| row.fact_id).collect::<Vec<_>>(),
        "ordinal" => rows.iter().map(|row| row.ordinal).collect::<Vec<_>>(),
        "name" => rows.iter().map(|row| row.class().identity.name.clone()).collect::<Vec<_>>(),
        "path" => rows.iter().map(|row| row.class().identity.path.clone()).collect::<Vec<_>>(),
        "start_line" => rows.iter().map(|row| row.class().identity.span.start_line as u64).collect::<Vec<_>>(),
        "start_column" => rows.iter().map(|row| row.class().identity.span.start_column as u64).collect::<Vec<_>>(),
        "end_line" => rows.iter().map(|row| row.class().identity.span.end_line as u64).collect::<Vec<_>>(),
        "end_column" => rows.iter().map(|row| row.class().identity.span.end_column as u64).collect::<Vec<_>>(),
        "is_test" => rows.iter().map(|row| row.class().identity.is_test).collect::<Vec<_>>(),
        "source" => rows.iter().map(|row| row.class().identity.source.clone()).collect::<Vec<_>>(),
        "scope" => rows.iter().map(|row| row.class().identity.scope.clone()).collect::<Vec<_>>(),
        "visibility" => rows.iter().map(|row| row.class().identity.visibility.clone()).collect::<Vec<_>>(),
    ]
}

fn class_measure_frame(rows: &[NestedRow<'_, ClassAnalysisRecord>]) -> PolarsResult<DataFrame> {
    df![
        "has_explicit_registry_name" => rows.iter().map(|row| row.class().declaration.has_explicit_registry_name).collect::<Vec<_>>(),
        "has_instance_fields" => rows.iter().map(|row| row.class().shape.has_instance_fields).collect::<Vec<_>>(),
        "field_count" => rows.iter().map(|row| row.class().shape.field_count as u64).collect::<Vec<_>>(),
        "has_inherited_fields" => rows.iter().map(|row| row.class().shape.has_inherited_fields).collect::<Vec<_>>(),
        "descendant_count" => rows.iter().map(|row| row.class().shape.descendant_count as u64).collect::<Vec<_>>(),
        "duplicate_component_alias_count" => rows.iter().map(|row| row.class().relations.duplicate_component_alias_count as u64).collect::<Vec<_>>(),
        "proposed_model_destination" => rows.iter().map(|row| row.class().model.proposed_model_destination.clone()).collect::<Vec<_>>(),
    ]
}

fn class_flag_frame(rows: &[NestedRow<'_, ClassAnalysisRecord>]) -> PolarsResult<DataFrame> {
    df![
        "is_protocol" => rows.iter().map(|row| row.class().declaration.is_protocol).collect::<Vec<_>>(),
        "is_instantiated" => rows.iter().map(|row| row.class().shape.is_instantiated).collect::<Vec<_>>(),
        "is_exported" => rows.iter().map(|row| row.class().shape.is_exported).collect::<Vec<_>>(),
        "only_cross_module_reference_is_subclass" => rows.iter().map(|row| row.class().relations.only_cross_module_reference_is_subclass).collect::<Vec<_>>(),
        "is_pass_through_layer" => rows.iter().map(|row| row.class().relations.is_pass_through_layer).collect::<Vec<_>>(),
        "base_is_removable_overlap" => rows.iter().map(|row| row.class().relations.base_is_removable_overlap).collect::<Vec<_>>(),
        "has_redundant_direct_base" => rows.iter().map(|row| row.class().relations.has_redundant_direct_base).collect::<Vec<_>>(),
        "has_noncooperative_concrete_collision" => rows.iter().map(|row| row.class().relations.has_noncooperative_concrete_collision).collect::<Vec<_>>(),
        "is_declarative_model" => rows.iter().map(|row| row.class().model.is_declarative_model).collect::<Vec<_>>(),
        "is_dataclass" => rows.iter().map(|row| row.class().model.is_dataclass).collect::<Vec<_>>(),
        "has_ordinary_behavior" => rows.iter().map(|row| row.class().model.has_ordinary_behavior).collect::<Vec<_>>(),
        "directly_inherits_pydantic_base_model" => rows.iter().map(|row| row.class().model.directly_inherits_pydantic_base_model).collect::<Vec<_>>(),
        "inherits_approved_model_foundation" => rows.iter().map(|row| row.class().model.inherits_approved_model_foundation).collect::<Vec<_>>(),
    ]
}

pub(super) fn method_rows(records: &[ClassRecord]) -> Vec<MethodRow<'_, MethodRecord>> {
    class_rows(records)
        .into_iter()
        .flat_map(|row| {
            row.value
                .declaration
                .methods
                .iter()
                .enumerate()
                .map(move |(ordinal, method)| MethodRow {
                    id: format!("{}:method:{ordinal}", row.id),
                    class_id: row.id.clone(),
                    ordinal: ordinal as u64,
                    method,
                })
        })
        .collect()
}

pub(super) fn method_frame(records: &[ClassRecord]) -> PolarsResult<DataFrame> {
    let rows = method_rows(records);
    combined_frame(
        rows.len(),
        [method_identity_frame(&rows)?, method_behavior_frame(&rows)?],
    )
}

pub(super) fn class_evidence_frame(records: &[ClassRecord]) -> PolarsResult<DataFrame> {
    evidence_relation(records, "fact_id", fact_key, |record| &record.evidence)
}

fn method_identity_frame(rows: &[MethodRow<'_, MethodRecord>]) -> PolarsResult<DataFrame> {
    df![
        "method_id" => rows.iter().map(|row| row.id.clone()).collect::<Vec<_>>(),
        "class_id" => rows.iter().map(|row| row.class_id.clone()).collect::<Vec<_>>(),
        "ordinal" => rows.iter().map(|row| row.ordinal).collect::<Vec<_>>(),
        "name" => rows.iter().map(|row| row.method.identity.name.clone()).collect::<Vec<_>>(),
        "path" => rows.iter().map(|row| row.method.identity.span.path.clone()).collect::<Vec<_>>(),
        "start_line" => rows.iter().map(|row| row.method.identity.span.start_line as u64).collect::<Vec<_>>(),
        "start_column" => rows.iter().map(|row| row.method.identity.span.start_column as u64).collect::<Vec<_>>(),
        "end_line" => rows.iter().map(|row| row.method.identity.span.end_line as u64).collect::<Vec<_>>(),
        "end_column" => rows.iter().map(|row| row.method.identity.span.end_column as u64).collect::<Vec<_>>(),
        "source" => rows.iter().map(|row| row.method.identity.source.clone()).collect::<Vec<_>>(),
    ]
}

fn method_behavior_frame(rows: &[MethodRow<'_, MethodRecord>]) -> PolarsResult<DataFrame> {
    df![
        "region" => rows.iter().map(|row| row.method.identity.region as u64).collect::<Vec<_>>(),
        "kind" => rows.iter().map(|row| row.method.identity.kind.clone()).collect::<Vec<_>>(),
        "visibility" => rows.iter().map(|row| row.method.identity.visibility.clone()).collect::<Vec<_>>(),
        "is_protocol_name" => rows.iter().map(|row| row.method.behavior.is_protocol_name).collect::<Vec<_>>(),
        "reads_receiver" => rows.iter().map(|row| row.method.behavior.reads_receiver).collect::<Vec<_>>(),
        "reads_receiver_state" => rows.iter().map(|row| row.method.behavior.reads_receiver_state).collect::<Vec<_>>(),
    ]
}
