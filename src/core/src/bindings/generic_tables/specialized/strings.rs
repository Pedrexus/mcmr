use super::super::GenericTables;
use super::attributes::empty_value_frame;
use super::frames::{FactColumnOrder, combined_frame, coordinate, fact_frame, nested_rows};
use crate::bindings::frames::frame_result;
use crate::bindings::frames::located::located_fact;
use crate::families::{StringExpression, StringExpressionRecord};
use polars::prelude::*;

mod semantics;

use semantics::{
    literal_fragments, repeated_literal, repetitions, runtime_value, string_kind, string_node,
    wraps_single_line,
};

located_fact!(StringExpressionRecord);

struct StringRow<'record> {
    fact_order: u64,
    fact: &'record StringExpressionRecord,
    ordinal: u64,
    record_id: String,
    expression: &'record StringExpression,
}

pub(crate) fn string_expressions(
    records: &[StringExpressionRecord],
) -> Result<GenericTables, String> {
    let rows = string_rows(records);
    Ok(GenericTables {
        facts: frame_result(string_fact_frame(records))?,
        records: frame_result(string_record_frame(&rows))?,
        values: frame_result(empty_value_frame())?,
    })
}

fn string_rows(records: &[StringExpressionRecord]) -> Vec<StringRow<'_>> {
    nested_rows(
        records,
        |fact| &fact.expressions,
        |fact_order, fact, ordinal, expression| StringRow {
            fact_order,
            fact,
            ordinal,
            record_id: format!("{}/expressions:{ordinal}", fact.key),
            expression,
        },
    )
}

fn string_fact_frame(records: &[StringExpressionRecord]) -> PolarsResult<DataFrame> {
    fact_frame(
        records,
        "expressions",
        records
            .iter()
            .map(|record| record.expressions.len() as i64)
            .collect(),
        FactColumnOrder::EvidenceFirst,
    )
}

fn string_record_frame(rows: &[StringRow<'_>]) -> PolarsResult<DataFrame> {
    let count = rows.len();
    combined_frame(
        count,
        [
            string_record_identity_frame(rows)?,
            string_record_expression_frame(rows)?,
            string_record_node_frame(rows)?,
            string_record_value_frame(rows)?,
        ],
    )
}

fn string_record_identity_frame(rows: &[StringRow<'_>]) -> PolarsResult<DataFrame> {
    let count = rows.len();
    df![
        "fact_order" => rows.iter().map(|row| row.fact_order).collect::<Vec<_>>(),
        "fact_id" => rows.iter().map(|row| row.fact.key.as_str()).collect::<Vec<_>>(),
        "relation" => vec!["expressions"; count],
        "parent_id" => rows.iter().map(|row| row.fact.key.as_str()).collect::<Vec<_>>(),
        "record_id" => rows.iter().map(|row| row.record_id.as_str()).collect::<Vec<_>>(),
        "ordinal" => rows.iter().map(|row| row.ordinal).collect::<Vec<_>>(),
        "confidence" => vec![None::<f64>; count],
        "detail" => vec![None::<&str>; count],
    ]
}

fn string_record_expression_frame(rows: &[StringRow<'_>]) -> PolarsResult<DataFrame> {
    df![
        "kind" => rows.iter().map(|row| string_kind(row.expression)).collect::<Vec<_>>(),
        "literal" => rows.iter().map(|row| repeated_literal(row.expression)).collect::<Vec<_>>(),
        "literal_fragment_count" => rows.iter().map(|row| literal_fragments(row.expression)).collect::<Vec<_>>(),
    ]
}

fn string_record_value_frame(rows: &[StringRow<'_>]) -> PolarsResult<DataFrame> {
    let count = rows.len();
    df![
        "repetition_count" => rows.iter().map(|row| repetitions(row.expression)).collect::<Vec<_>>(),
        "runtime_value" => rows.iter().map(|row| runtime_value(row.expression)).collect::<Vec<_>>(),
        "signal" => vec![None::<&str>; count],
        "source" => vec![None::<&str>; count],
        "wraps_single_runtime_line" => rows.iter().map(|row| wraps_single_line(row.expression)).collect::<Vec<_>>(),
    ]
}

fn string_record_node_frame(rows: &[StringRow<'_>]) -> PolarsResult<DataFrame> {
    df![
        "node.id" => rows.iter().map(|row| string_node(row.expression).id.as_str()).collect::<Vec<_>>(),
        "node.kind" => rows.iter().map(|row| string_node(row.expression).kind.as_str()).collect::<Vec<_>>(),
        "node.span.end_column" => rows.iter().map(|row| coordinate(string_node(row.expression).span.end_column)).collect::<Vec<_>>(),
        "node.span.end_line" => rows.iter().map(|row| coordinate(string_node(row.expression).span.end_line)).collect::<Vec<_>>(),
        "node.span.path" => rows.iter().map(|row| string_node(row.expression).span.path.as_str()).collect::<Vec<_>>(),
        "node.span.start_column" => rows.iter().map(|row| coordinate(string_node(row.expression).span.start_column)).collect::<Vec<_>>(),
        "node.span.start_line" => rows.iter().map(|row| coordinate(string_node(row.expression).span.start_line)).collect::<Vec<_>>(),
        "node.text" => rows.iter().map(|row| string_node(row.expression).text.as_str()).collect::<Vec<_>>(),
    ]
}
