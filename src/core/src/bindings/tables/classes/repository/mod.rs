use super::core::class_relation_rows;
use crate::bindings::frames::string_values::{StringValueColumns, selected_string_value_frame};
use crate::bindings::relations::NestedRow;
use crate::classes::{
    AttributeProjectionRecord, ClassRecord, CoupledTypeGroupRecord, ModelFileRecord,
};
use polars::prelude::*;

impl<'a> NestedRow<'a, CoupledTypeGroupRecord> {
    fn group(&self) -> &'a CoupledTypeGroupRecord {
        self.value
    }
}

fn coupled_group_rows(records: &[ClassRecord]) -> Vec<NestedRow<'_, CoupledTypeGroupRecord>> {
    class_relation_rows(records, "coupled_group", |record| {
        &record.relations.coupled_groups
    })
}

pub(super) fn coupled_group_frame(records: &[ClassRecord]) -> PolarsResult<DataFrame> {
    let rows = coupled_group_rows(records);
    df![
        "group_id" => rows.iter().map(|row| row.id.clone()).collect::<Vec<_>>(),
        "fact_id" => rows.iter().map(|row| row.fact_id).collect::<Vec<_>>(),
        "ordinal" => rows.iter().map(|row| row.ordinal).collect::<Vec<_>>(),
        "prefix" => rows.iter().map(|row| row.group().prefix.clone()).collect::<Vec<_>>(),
        "path" => rows.iter().map(|row| row.group().span.path.clone()).collect::<Vec<_>>(),
        "start_line" => rows.iter().map(|row| row.group().span.start_line as u64).collect::<Vec<_>>(),
        "start_column" => rows.iter().map(|row| row.group().span.start_column as u64).collect::<Vec<_>>(),
        "end_line" => rows.iter().map(|row| row.group().span.end_line as u64).collect::<Vec<_>>(),
        "end_column" => rows.iter().map(|row| row.group().span.end_column as u64).collect::<Vec<_>>(),
        "type_count" => rows.iter().map(|row| row.group().type_count as u64).collect::<Vec<_>>(),
        "maximum_type_lines" => rows.iter().map(|row| row.group().maximum_type_lines as u64).collect::<Vec<_>>(),
        "coimporting_module_count" => rows.iter().map(|row| row.group().coimporting_module_count as u64).collect::<Vec<_>>(),
    ]
}

pub(super) fn coupled_group_suffix_frame(records: &[ClassRecord]) -> PolarsResult<DataFrame> {
    selected_string_value_frame(
        StringValueColumns {
            id: "group_id",
            value: "suffix",
        },
        coupled_group_rows(records)
            .into_iter()
            .map(|row| (row.id, row.value)),
        |group| &group.role_suffixes,
    )
}

impl<'a> NestedRow<'a, ModelFileRecord> {
    fn model_file(&self) -> &'a ModelFileRecord {
        self.value
    }
}

fn model_file_rows(records: &[ClassRecord]) -> Vec<NestedRow<'_, ModelFileRecord>> {
    class_relation_rows(records, "model_file", |record| {
        &record.relations.model_files
    })
}

pub(super) fn model_file_frame(records: &[ClassRecord]) -> PolarsResult<DataFrame> {
    let rows = model_file_rows(records);
    df![
        "model_file_id" => rows.iter().map(|row| row.id.clone()).collect::<Vec<_>>(),
        "fact_id" => rows.iter().map(|row| row.fact_id).collect::<Vec<_>>(),
        "ordinal" => rows.iter().map(|row| row.ordinal).collect::<Vec<_>>(),
        "path" => rows.iter().map(|row| row.model_file().path.clone()).collect::<Vec<_>>(),
        "start_line" => rows.iter().map(|row| row.model_file().span.start_line as u64).collect::<Vec<_>>(),
        "start_column" => rows.iter().map(|row| row.model_file().span.start_column as u64).collect::<Vec<_>>(),
        "end_line" => rows.iter().map(|row| row.model_file().span.end_line as u64).collect::<Vec<_>>(),
        "end_column" => rows.iter().map(|row| row.model_file().span.end_column as u64).collect::<Vec<_>>(),
        "top_level_class_count" => rows.iter().map(|row| row.model_file().top_level_class_count as u64).collect::<Vec<_>>(),
        "model_class_count" => rows.iter().map(|row| row.model_file().model_class_count as u64).collect::<Vec<_>>(),
        "is_package_initializer" => rows.iter().map(|row| row.model_file().is_package_initializer).collect::<Vec<_>>(),
    ]
}

impl<'a> NestedRow<'a, AttributeProjectionRecord> {
    fn projection(&self) -> &'a AttributeProjectionRecord {
        self.value
    }
}

fn projection_rows(records: &[ClassRecord]) -> Vec<NestedRow<'_, AttributeProjectionRecord>> {
    class_relation_rows(records, "projection", |record| {
        &record.relations.projection_groups
    })
}

pub(super) fn projection_frame(records: &[ClassRecord]) -> PolarsResult<DataFrame> {
    let rows = projection_rows(records);
    df![
        "projection_id" => rows.iter().map(|row| row.id.clone()).collect::<Vec<_>>(),
        "fact_id" => rows.iter().map(|row| row.fact_id).collect::<Vec<_>>(),
        "ordinal" => rows.iter().map(|row| row.ordinal).collect::<Vec<_>>(),
        "root" => rows.iter().map(|row| row.projection().root.clone()).collect::<Vec<_>>(),
        "path" => rows.iter().map(|row| row.projection().span.path.clone()).collect::<Vec<_>>(),
        "start_line" => rows.iter().map(|row| row.projection().span.start_line as u64).collect::<Vec<_>>(),
        "start_column" => rows.iter().map(|row| row.projection().span.start_column as u64).collect::<Vec<_>>(),
        "end_line" => rows.iter().map(|row| row.projection().span.end_line as u64).collect::<Vec<_>>(),
        "end_column" => rows.iter().map(|row| row.projection().span.end_column as u64).collect::<Vec<_>>(),
    ]
}

#[derive(Clone, Copy)]
pub(super) enum ProjectionValue {
    Attribute,
    OutputKey,
}

pub(super) fn projection_value_frame(
    records: &[ClassRecord],
    field: ProjectionValue,
) -> PolarsResult<DataFrame> {
    selected_string_value_frame(
        StringValueColumns {
            id: "projection_id",
            value: "value",
        },
        projection_rows(records)
            .into_iter()
            .map(|row| (row.id, row.value)),
        |projection| match field {
            ProjectionValue::Attribute => &projection.attribute_names,
            ProjectionValue::OutputKey => &projection.output_keys,
        },
    )
}
