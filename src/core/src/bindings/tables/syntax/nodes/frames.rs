use super::traversal::syntax_node_rows;
use crate::bindings::frames::combined_frame;
use crate::bindings::rows::syntax::SyntaxNodeRow;
use crate::syntax::{PackedSyntaxRecord, SyntaxRecord};
use polars::prelude::*;

struct SyntaxChildRow<'record> {
    fact_id: &'record str,
    parent: u64,
    order: u64,
    child: u64,
}

pub(in crate::bindings::tables::syntax) fn syntax_node_frame(
    records: &[SyntaxRecord],
) -> PolarsResult<DataFrame> {
    let rows = syntax_node_rows(records);
    combined_frame(
        rows.len(),
        [syntax_identity_frame(&rows)?, syntax_location_frame(&rows)?],
    )
}

fn syntax_identity_frame(
    rows: &[SyntaxNodeRow<'_, PackedSyntaxRecord>],
) -> PolarsResult<DataFrame> {
    df![
        "fact_order" => rows.iter().map(|row| row.fact_order).collect::<Vec<_>>(),
        "fact_id" => rows.iter().map(|row| row.fact_id).collect::<Vec<_>>(),
        "node_id" => rows.iter().map(|row| format!("{}:{}", row.fact_id, row.traversal.ordinal)).collect::<Vec<_>>(),
        "parent_id" => rows.iter().map(|row| row.traversal.parent.map_or_else(String::new, |parent| format!("{}:{parent}", row.fact_id))).collect::<Vec<_>>(),
        "ordinal" => rows.iter().map(|row| row.traversal.ordinal).collect::<Vec<_>>(),
        "subtree_end" => rows.iter().map(|row| row.traversal.subtree_end).collect::<Vec<_>>(),
        "depth" => rows.iter().map(|row| row.traversal.depth).collect::<Vec<_>>(),
        "kind" => rows.iter().map(|row| row.node.0.clone()).collect::<Vec<_>>(),
        "name" => rows.iter().map(|row| row.node.1.clone()).collect::<Vec<_>>(),
    ]
}

fn syntax_location_frame(
    rows: &[SyntaxNodeRow<'_, PackedSyntaxRecord>],
) -> PolarsResult<DataFrame> {
    df![
        "path" => rows.iter().map(|row| row.path).collect::<Vec<_>>(),
        "start_line" => rows.iter().map(|row| row.node.2 as u64).collect::<Vec<_>>(),
        "start_column" => rows.iter().map(|row| row.node.3 as u64).collect::<Vec<_>>(),
        "end_line" => rows.iter().map(|row| row.node.4 as u64).collect::<Vec<_>>(),
        "end_column" => rows.iter().map(|row| row.node.5 as u64).collect::<Vec<_>>(),
        "byte_start" => rows.iter().map(|row| row.bytes.start).collect::<Vec<_>>(),
        "byte_length" => rows.iter().map(|row| row.bytes.length).collect::<Vec<_>>(),
    ]
}

pub(in crate::bindings::tables::syntax) fn syntax_child_frame(
    records: &[SyntaxRecord],
) -> PolarsResult<DataFrame> {
    let rows = syntax_child_rows(records);
    df![
        "fact_id" => rows.iter().map(|row| row.fact_id).collect::<Vec<_>>(),
        "parent_ordinal" => rows.iter().map(|row| row.parent).collect::<Vec<_>>(),
        "child_order" => rows.iter().map(|row| row.order).collect::<Vec<_>>(),
        "child_ordinal" => rows.iter().map(|row| row.child).collect::<Vec<_>>(),
    ]
}

fn syntax_child_rows(records: &[SyntaxRecord]) -> Vec<SyntaxChildRow<'_>> {
    records.iter().flat_map(record_child_rows).collect()
}

fn record_child_rows(record: &SyntaxRecord) -> Vec<SyntaxChildRow<'_>> {
    record
        .nodes
        .iter()
        .enumerate()
        .flat_map(|(parent, node)| {
            node.6
                .iter()
                .enumerate()
                .map(move |(order, child)| SyntaxChildRow {
                    fact_id: &record.key,
                    parent: parent as u64,
                    order: order as u64,
                    child: *child as u64,
                })
        })
        .collect()
}
