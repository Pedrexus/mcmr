use crate::imports::ImportBindingRecord;
use crate::protocol::Node;
use polars::prelude::*;

struct ImportNodeRow<'record> {
    fact_id: &'record str,
    role: String,
    ordinal: u64,
    node: &'record Node,
}

pub(super) fn import_binding_node_frame(
    records: &[ImportBindingRecord],
) -> PolarsResult<DataFrame> {
    let rows = import_node_rows(records);
    df![
        "fact_id" => rows.iter().map(|row| row.fact_id).collect::<Vec<_>>(),
        "role" => rows.iter().map(|row| row.role.as_str()).collect::<Vec<_>>(),
        "ordinal" => rows.iter().map(|row| row.ordinal).collect::<Vec<_>>(),
        "node_id" => rows.iter().map(|row| row.node.id.clone()).collect::<Vec<_>>(),
        "path" => rows.iter().map(|row| row.node.span.path.clone()).collect::<Vec<_>>(),
        "start_line" => rows.iter().map(|row| row.node.span.start_line as u64).collect::<Vec<_>>(),
        "start_column" => rows.iter().map(|row| row.node.span.start_column as u64).collect::<Vec<_>>(),
        "end_line" => rows.iter().map(|row| row.node.span.end_line as u64).collect::<Vec<_>>(),
        "end_column" => rows.iter().map(|row| row.node.span.end_column as u64).collect::<Vec<_>>(),
        "kind" => rows.iter().map(|row| row.node.kind.clone()).collect::<Vec<_>>(),
        "text" => rows.iter().map(|row| row.node.text.clone()).collect::<Vec<_>>(),
    ]
}

fn import_node_rows(records: &[ImportBindingRecord]) -> Vec<ImportNodeRow<'_>> {
    records.iter().flat_map(import_record_node_rows).collect()
}

fn import_record_node_rows(record: &ImportBindingRecord) -> Vec<ImportNodeRow<'_>> {
    let mut rows = [
        ("declaration", record.context.declaration.as_ref()),
        ("binding", record.context.binding.as_ref()),
        ("module", record.context.module_node.as_ref()),
    ]
    .into_iter()
    .filter_map(|(role, node)| {
        node.map(|held| ImportNodeRow {
            fact_id: &record.identity.key,
            role: role.to_owned(),
            ordinal: 0,
            node: held,
        })
    })
    .collect::<Vec<_>>();
    rows.extend(
        record
            .context
            .references
            .iter()
            .enumerate()
            .map(|(ordinal, node)| ImportNodeRow {
                fact_id: &record.identity.key,
                role: "reference".to_owned(),
                ordinal: ordinal as u64,
                node,
            }),
    );
    rows
}
