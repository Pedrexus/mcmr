use crate::bindings::frames::evidence_relation;
use crate::bindings::frames::located::{LocatedFact, fact_columns, fact_key};
use crate::imports::ImportBindingRecord;
use nodes::import_binding_node_frame;
use polars::prelude::*;
use pyo3::prelude::*;
use pyo3_polars::PyDataFrame;

impl LocatedFact for ImportBindingRecord {
    fn key(&self) -> &str {
        &self.identity.key
    }

    fn path(&self) -> &str {
        &self.identity.span.path
    }

    fn start_line(&self) -> u64 {
        self.identity.span.start_line as u64
    }

    fn start_column(&self) -> u64 {
        self.identity.span.start_column as u64
    }

    fn end_line(&self) -> u64 {
        self.identity.span.end_line as u64
    }

    fn end_column(&self) -> u64 {
        self.identity.span.end_column as u64
    }

    fn language(&self) -> &str {
        &self.identity.language
    }
}

mod nodes;

#[pyclass]
pub(in crate::bindings) struct ImportBindingTables {
    facts: DataFrame,
    nodes: DataFrame,
    evidence: DataFrame,
}

frame_getters!(ImportBindingTables {
    facts,
    nodes,
    evidence,
});

table_builder!(
    ImportBindingTables,
    ImportBindingRecord {
        facts: import_binding_fact_frame,
        nodes: import_binding_node_frame,
        evidence: import_binding_evidence_frame,
    }
);

fn import_binding_fact_frame(records: &[ImportBindingRecord]) -> PolarsResult<DataFrame> {
    let mut columns = fact_columns(records)?;
    columns.extend(import_binding_text_columns(records)?.into_columns());
    columns.extend(import_binding_measure_columns(records)?.into_columns());
    DataFrame::new(records.len(), columns)
}

fn import_binding_text_columns(records: &[ImportBindingRecord]) -> PolarsResult<DataFrame> {
    df![
        "name" => records.iter().map(|record| record.identity.name.as_str()).collect::<Vec<_>>(),
        "module" => records.iter().map(|record| record.identity.module.as_str()).collect::<Vec<_>>(),
        "imported_name" => records.iter().map(|record| record.identity.imported_name.as_str()).collect::<Vec<_>>(),
        "importer_module" => records.iter().map(|record| record.context.importer_module.as_str()).collect::<Vec<_>>(),
        "declaration_id" => records.iter().map(|record| record.context.declaration.as_ref().map(|node| node.id.as_str()).unwrap_or("")).collect::<Vec<_>>(),
        "declaration_text" => records.iter().map(|record| record.context.declaration.as_ref().map(|node| node.text.as_str()).unwrap_or("")).collect::<Vec<_>>(),
        "binding_id" => records.iter().map(|record| record.context.binding.as_ref().map(|node| node.id.as_str()).unwrap_or("")).collect::<Vec<_>>(),
        "module_node_id" => records.iter().map(|record| record.context.module_node.as_ref().map(|node| node.id.as_str()).unwrap_or("")).collect::<Vec<_>>(),
    ]
}

fn import_binding_measure_columns(records: &[ImportBindingRecord]) -> PolarsResult<DataFrame> {
    df![
        "reference_count" => records.iter().map(|record| record.context.reference_count as u64).collect::<Vec<_>>(),
        "relative_level" => records.iter().map(|record| record.context.relative_level as u64).collect::<Vec<_>>(),
        "has_qualifying_use" => records.iter().map(|record| record.context.has_qualifying_use).collect::<Vec<_>>(),
        "is_external" => records.iter().map(|record| record.ownership.is_external).collect::<Vec<_>>(),
        "is_reexported" => records.iter().map(|record| record.ownership.is_reexported).collect::<Vec<_>>(),
        "is_type_only" => records.iter().map(|record| record.ownership.is_type_only).collect::<Vec<_>>(),
        "has_documented_side_effect" => records.iter().map(|record| record.ownership.has_documented_side_effect).collect::<Vec<_>>(),
        "is_relative" => records.iter().map(|record| record.ownership.is_relative).collect::<Vec<_>>(),
        "is_project_owned" => records.iter().map(|record| record.ownership.is_project_owned).collect::<Vec<_>>(),
        "is_sole_binding" => records.iter().map(|record| record.shape.is_sole_binding).collect::<Vec<_>>(),
        "has_private_module_component" => records.iter().map(|record| record.shape.has_private_module_component).collect::<Vec<_>>(),
        "is_private_member" => records.iter().map(|record| record.shape.is_private_member).collect::<Vec<_>>(),
        "is_private_uppercase_constant" => records.iter().map(|record| record.shape.is_private_uppercase_constant).collect::<Vec<_>>(),
        "is_wildcard" => records.iter().map(|record| record.shape.is_wildcard).collect::<Vec<_>>(),
    ]
}

fn import_binding_evidence_frame(records: &[ImportBindingRecord]) -> PolarsResult<DataFrame> {
    evidence_relation(records, "fact_id", fact_key, |record| {
        &record.identity.evidence
    })
}
