use super::facts::normalized_fact_columns;
use crate::bindings::generic_tables::normalization::support::{ScalarValue, ValueRow};
use polars::prelude::*;

pub(crate) fn value_frame(rows: &[ValueRow]) -> Result<DataFrame, String> {
    let mut columns = normalized_fact_columns(rows)?;
    for frame in [
        value_location_frame(rows)?,
        value_container_frame(rows)?,
        value_payload_frame(rows)?,
    ] {
        columns.extend(frame.into_columns());
    }
    DataFrame::new(rows.len(), columns).map_err(|failure| failure.to_string())
}

fn value_location_frame(rows: &[ValueRow]) -> Result<DataFrame, String> {
    df![
        "relation" => rows.iter().map(|row| row.location.relation.as_str()).collect::<Vec<_>>(),
        "parent_id" => rows.iter().map(|row| row.location.parent_id.as_str()).collect::<Vec<_>>(),
        "container_id" => rows.iter().map(|row| row.location.container.id.as_str()).collect::<Vec<_>>(),
    ]
    .map_err(|failure| failure.to_string())
}

fn value_container_frame(rows: &[ValueRow]) -> Result<DataFrame, String> {
    df![
        "container_ordinal" => rows.iter().map(|row| row.location.container.ordinal).collect::<Vec<_>>(),
        "container_length" => rows.iter().map(|row| row.location.container.length).collect::<Vec<_>>(),
        "entry_kind" => rows.iter().map(|row| row.location.entry_kind.as_str()).collect::<Vec<_>>(),
        "value_id" => rows.iter().map(|row| row.location.value_id.as_str()).collect::<Vec<_>>(),
        "ordinal" => rows.iter().map(|row| row.location.ordinal).collect::<Vec<_>>(),
        "map_key" => rows.iter().map(|row| row.location.map_key.as_deref()).collect::<Vec<_>>(),
    ]
    .map_err(|failure| failure.to_string())
}

fn value_payload_frame(rows: &[ValueRow]) -> Result<DataFrame, String> {
    df![
        "string_value" => rows.iter().map(|row| row.value.as_ref().and_then(ScalarValue::text)).collect::<Vec<_>>(),
        "integer_value" => rows.iter().map(|row| row.value.as_ref().and_then(ScalarValue::integer)).collect::<Vec<_>>(),
        "float_value" => rows.iter().map(|row| row.value.as_ref().and_then(ScalarValue::float)).collect::<Vec<_>>(),
        "boolean_value" => rows.iter().map(|row| row.value.as_ref().and_then(ScalarValue::boolean)).collect::<Vec<_>>(),
    ]
    .map_err(|failure| failure.to_string())
}
