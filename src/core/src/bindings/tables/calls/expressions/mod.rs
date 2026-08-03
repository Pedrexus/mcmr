use super::rows::call_rows;
use crate::bindings::frames::combined_frame;
use crate::calls::CallRecord;
use collector::ExpressionCollector;
use place::ExpressionPlace;
use polars::prelude::*;
use relations::ancestry::ExpressionAncestryRow;
use relations::mapping::MappingRow;
use rows::ExpressionRow;

mod collector;
mod place;
mod relations;
mod rows;

fn expression_rows(
    records: &[CallRecord],
) -> (
    Vec<ExpressionRow<'_>>,
    Vec<ExpressionAncestryRow>,
    Vec<MappingRow>,
) {
    let mut expressions = Vec::new();
    let mut ancestry = Vec::new();
    let mut mappings = Vec::new();
    for row in call_rows(records) {
        let call = row.call();
        let collector = collect_expressions(row.id, call);
        expressions.extend(collector.expressions);
        ancestry.extend(collector.ancestry);
        mappings.extend(collector.mappings);
    }
    (expressions, ancestry, mappings)
}

fn collect_expressions<'record>(
    call_id: String,
    call: &'record crate::calls::CallSite,
) -> ExpressionCollector<'record> {
    let mut collector = ExpressionCollector::new(call_id);
    for (ordinal, argument) in call.arguments.iter().enumerate() {
        collector.add(argument, ExpressionPlace::root("argument", ordinal), &[]);
    }
    if let Some(receiver) = &call.receiver {
        collector.add(receiver, ExpressionPlace::root("receiver", 0), &[]);
    }
    collector
}

pub(super) fn expression_frames(
    records: &[CallRecord],
) -> PolarsResult<(DataFrame, DataFrame, DataFrame)> {
    let (rows, ancestry, mappings) = expression_rows(records);
    Ok((
        expression_frame(&rows)?,
        ancestry_frame(&ancestry)?,
        mapping_frame(&mappings)?,
    ))
}

fn expression_frame(rows: &[ExpressionRow<'_>]) -> PolarsResult<DataFrame> {
    combined_frame(
        rows.len(),
        [
            expression_identity_frame(rows)?,
            expression_node_frame(rows)?,
        ],
    )
}

fn expression_identity_frame(rows: &[ExpressionRow<'_>]) -> PolarsResult<DataFrame> {
    df![
        "expression_id" => rows.iter().map(|row| row.id.clone()).collect::<Vec<_>>(),
        "call_id" => rows.iter().map(|row| row.call_id.clone()).collect::<Vec<_>>(),
        "preorder" => (0..rows.len() as u64).collect::<Vec<_>>(),
        "parent_expression_id" => rows.iter().map(|row| row.place.parent_id.clone()).collect::<Vec<_>>(),
        "relation" => rows.iter().map(|row| row.place.relation.clone()).collect::<Vec<_>>(),
        "ordinal" => rows.iter().map(|row| row.place.ordinal as u64).collect::<Vec<_>>(),
        "root_relation" => rows.iter().map(|row| row.place.root_relation.clone()).collect::<Vec<_>>(),
        "root_ordinal" => rows.iter().map(|row| row.place.root_ordinal as u64).collect::<Vec<_>>(),
        "depth" => rows.iter().map(|row| row.place.depth as u64).collect::<Vec<_>>(),
        "text" => rows.iter().map(|row| row.expression.text.clone()).collect::<Vec<_>>(),
        "qualified_name" => rows.iter().map(|row| row.expression.qualified_name.clone()).collect::<Vec<_>>(),
        "literal_kind" => rows.iter().map(|row| row.expression.literal_kind.clone()).collect::<Vec<_>>(),
        "resolved_type" => rows.iter().map(|row| row.expression.resolved_type.clone()).collect::<Vec<_>>(),
    ]
}

fn expression_node_frame(rows: &[ExpressionRow<'_>]) -> PolarsResult<DataFrame> {
    df![
        "node_id" => rows.iter().map(|row| row.expression.node.as_ref().map(|node| node.id.clone())).collect::<Vec<_>>(),
        "node_path" => rows.iter().map(|row| row.expression.node.as_ref().map(|node| node.span.path.clone())).collect::<Vec<_>>(),
        "node_start_line" => rows.iter().map(|row| row.expression.node.as_ref().map(|node| node.span.start_line as u64)).collect::<Vec<_>>(),
        "node_start_column" => rows.iter().map(|row| row.expression.node.as_ref().map(|node| node.span.start_column as u64)).collect::<Vec<_>>(),
        "node_end_line" => rows.iter().map(|row| row.expression.node.as_ref().map(|node| node.span.end_line as u64)).collect::<Vec<_>>(),
        "node_end_column" => rows.iter().map(|row| row.expression.node.as_ref().map(|node| node.span.end_column as u64)).collect::<Vec<_>>(),
        "node_kind" => rows.iter().map(|row| row.expression.node.as_ref().map(|node| node.kind.clone())).collect::<Vec<_>>(),
        "node_text" => rows.iter().map(|row| row.expression.node.as_ref().map(|node| node.text.clone())).collect::<Vec<_>>(),
    ]
}

fn ancestry_frame(rows: &[ExpressionAncestryRow]) -> PolarsResult<DataFrame> {
    df![
        "call_id" => rows.iter().map(|row| row.call_id.clone()).collect::<Vec<_>>(),
        "descendant_expression_id" => rows.iter().map(|row| row.descendant_expression_id.clone()).collect::<Vec<_>>(),
        "step" => rows.iter().map(|row| row.step).collect::<Vec<_>>(),
        "parent_id" => rows.iter().map(|row| row.edge.parent_id.clone()).collect::<Vec<_>>(),
        "parent_kind" => rows.iter().map(|row| row.edge.parent_kind.clone()).collect::<Vec<_>>(),
        "child_expression_id" => rows.iter().map(|row| row.edge.child_id.clone()).collect::<Vec<_>>(),
        "relation" => rows.iter().map(|row| row.edge.relation.clone()).collect::<Vec<_>>(),
        "ordinal" => rows.iter().map(|row| row.edge.ordinal).collect::<Vec<_>>(),
    ]
}

fn mapping_frame(rows: &[MappingRow]) -> PolarsResult<DataFrame> {
    df![
        "expression_id" => rows.iter().map(|row| row.expression_id.clone()).collect::<Vec<_>>(),
        "ordinal" => rows.iter().map(|row| row.ordinal).collect::<Vec<_>>(),
        "key" => rows.iter().map(|row| row.key.clone()).collect::<Vec<_>>(),
        "value_expression_id" => rows.iter().map(|row| row.value_expression_id.clone()).collect::<Vec<_>>(),
    ]
}
