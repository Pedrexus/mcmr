use super::super::GenericTables;
use super::frames::{FactColumnOrder, combined_frame, coordinate, fact_frame, nested_rows};
use crate::bindings::frames::frame_result;
use crate::bindings::frames::located::located_fact;
use crate::families::AttributeAccessRecord;
use polars::prelude::*;
use row::AttributeRow;
use value::{AttributeValueRow, attribute_value_frame};

pub(super) use value::empty_value_frame;

mod origin;
mod row;
mod value;

located_fact!(AttributeAccessRecord);

pub(crate) fn attribute_accesses(
    records: &[AttributeAccessRecord],
) -> Result<GenericTables, String> {
    let rows = attribute_rows(records);
    Ok(GenericTables {
        facts: frame_result(attribute_fact_frame(records))?,
        records: frame_result(attribute_record_frame(&rows))?,
        values: frame_result(attribute_value_frame(&attribute_value_rows(&rows)))?,
    })
}

fn attribute_rows(records: &[AttributeAccessRecord]) -> Vec<AttributeRow<'_>> {
    nested_rows(
        records,
        |fact| &fact.accesses,
        |fact_order, fact, ordinal, access| AttributeRow {
            fact_order,
            fact,
            ordinal,
            record_id: format!("{}/accesses:{ordinal}", fact.key),
            access,
        },
    )
}

fn attribute_value_rows<'record>(
    rows: &'record [AttributeRow<'record>],
) -> Vec<AttributeValueRow<'record>> {
    rows.iter()
        .flat_map(AttributeValueRow::from_attribute)
        .collect()
}

fn attribute_fact_frame(records: &[AttributeAccessRecord]) -> PolarsResult<DataFrame> {
    fact_frame(
        records,
        "accesses",
        records
            .iter()
            .map(|record| record.accesses.len() as i64)
            .collect(),
        FactColumnOrder::RelationFirst,
    )
}

fn attribute_record_frame(rows: &[AttributeRow<'_>]) -> PolarsResult<DataFrame> {
    let count = rows.len();
    combined_frame(
        count,
        [
            attribute_record_identity_frame(rows)?,
            attribute_record_access_frame(rows)?,
            attribute_record_node_frame(rows)?,
            attribute_record_context_frame(rows)?,
        ],
    )
}

fn attribute_record_identity_frame(rows: &[AttributeRow<'_>]) -> PolarsResult<DataFrame> {
    let count = rows.len();
    df![
        "fact_order" => rows.iter().map(|row| row.fact_order).collect::<Vec<_>>(),
        "fact_id" => rows.iter().map(|row| row.fact.key.as_str()).collect::<Vec<_>>(),
        "relation" => vec!["accesses"; count],
        "parent_id" => rows.iter().map(|row| row.fact.key.as_str()).collect::<Vec<_>>(),
        "record_id" => rows.iter().map(|row| row.record_id.as_str()).collect::<Vec<_>>(),
        "ordinal" => rows.iter().map(|row| row.ordinal).collect::<Vec<_>>(),
        "confidence" => vec![None::<f64>; count],
        "detail" => vec![None::<&str>; count],
    ]
}

fn attribute_record_access_frame(rows: &[AttributeRow<'_>]) -> PolarsResult<DataFrame> {
    df![
        "is_inside_owning_class" => rows.iter().map(|row| row.access.is_inside_owning_class).collect::<Vec<_>>(),
        "is_protocol_name" => rows.iter().map(|row| row.access.is_protocol_name).collect::<Vec<_>>(),
        "name" => rows.iter().map(|row| row.access.name.as_str()).collect::<Vec<_>>(),
    ]
}

fn attribute_record_context_frame(rows: &[AttributeRow<'_>]) -> PolarsResult<DataFrame> {
    let count = rows.len();
    df![
        "receiver_kind" => rows.iter().map(|row| row.access.receiver.kind.as_str()).collect::<Vec<_>>(),
        "receiver_text" => rows.iter().map(|row| row.access.receiver.text.as_str()).collect::<Vec<_>>(),
        "receiver_type" => rows.iter().map(|row| row.access.receiver.type_name.as_str()).collect::<Vec<_>>(),
        "receiver_type_bases.length" => rows.iter().map(|row| row.access.receiver.type_bases.len() as i64).collect::<Vec<_>>(),
        "receiver_type_bases.present" => vec![true; count],
        "signal" => vec![None::<&str>; count],
        "source" => vec![None::<&str>; count],
        "visibility" => rows.iter().map(|row| row.access.visibility.as_str()).collect::<Vec<_>>(),
    ]
}

fn attribute_record_node_frame(rows: &[AttributeRow<'_>]) -> PolarsResult<DataFrame> {
    df![
        "node.id" => rows.iter().map(|row| row.access.node.id.as_str()).collect::<Vec<_>>(),
        "node.kind" => rows.iter().map(|row| row.access.node.kind.as_str()).collect::<Vec<_>>(),
        "node.span.end_column" => rows.iter().map(|row| coordinate(row.access.node.span.end_column)).collect::<Vec<_>>(),
        "node.span.end_line" => rows.iter().map(|row| coordinate(row.access.node.span.end_line)).collect::<Vec<_>>(),
        "node.span.path" => rows.iter().map(|row| row.access.node.span.path.as_str()).collect::<Vec<_>>(),
        "node.span.start_column" => rows.iter().map(|row| coordinate(row.access.node.span.start_column)).collect::<Vec<_>>(),
        "node.span.start_line" => rows.iter().map(|row| coordinate(row.access.node.span.start_line)).collect::<Vec<_>>(),
        "node.text" => rows.iter().map(|row| row.access.node.text.as_str()).collect::<Vec<_>>(),
    ]
}
