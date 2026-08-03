use super::super::frames::combined_frame;
use super::origin::AttributeValueOrigin;
use super::row::AttributeRow;
use polars::prelude::*;

pub(super) struct AttributeValueRow<'record> {
    pub(super) fact_order: u64,
    pub(super) fact_id: &'record str,
    pub(super) origin: AttributeValueOrigin,
    pub(super) value_id: String,
    pub(super) ordinal: u64,
    pub(super) value: &'record str,
}

pub(super) fn attribute_value_frame(rows: &[AttributeValueRow<'_>]) -> PolarsResult<DataFrame> {
    combined_frame(
        rows.len(),
        [
            attribute_value_location_frame(rows)?,
            attribute_value_payload_frame(rows)?,
        ],
    )
}

fn attribute_value_location_frame(rows: &[AttributeValueRow<'_>]) -> PolarsResult<DataFrame> {
    let count = rows.len();
    df![
        "fact_order" => rows.iter().map(|row| row.fact_order).collect::<Vec<_>>(),
        "fact_id" => rows.iter().map(|row| row.fact_id).collect::<Vec<_>>(),
        "relation" => vec!["accesses.receiver_type_bases"; count],
        "parent_id" => rows.iter().map(|row| row.origin.parent_id.as_str()).collect::<Vec<_>>(),
        "container_id" => rows.iter().map(|row| row.origin.container_id.as_str()).collect::<Vec<_>>(),
        "container_ordinal" => vec![None::<u64>; count],
        "container_length" => rows.iter().map(|row| Some(row.origin.container_length)).collect::<Vec<_>>(),
        "entry_kind" => vec!["value"; count],
        "value_id" => rows.iter().map(|row| row.value_id.as_str()).collect::<Vec<_>>(),
        "ordinal" => rows.iter().map(|row| row.ordinal).collect::<Vec<_>>(),
        "map_key" => vec![None::<&str>; count],
    ]
}

fn attribute_value_payload_frame(rows: &[AttributeValueRow<'_>]) -> PolarsResult<DataFrame> {
    let count = rows.len();
    df![
        "string_value" => rows.iter().map(|row| row.value).collect::<Vec<_>>(),
        "integer_value" => vec![None::<i64>; count],
        "float_value" => vec![None::<f64>; count],
        "boolean_value" => vec![None::<bool>; count],
    ]
}

pub(crate) fn empty_value_frame() -> PolarsResult<DataFrame> {
    attribute_value_frame(&[])
}

impl<'record> AttributeValueRow<'record> {
    pub(super) fn from_attribute(
        row: &'record AttributeRow<'record>,
    ) -> impl Iterator<Item = Self> + 'record {
        let origin = AttributeValueOrigin::new(row);
        row.access
            .receiver
            .type_bases
            .iter()
            .enumerate()
            .map(move |(ordinal, value)| Self::new(row, ordinal, value, &origin))
    }

    fn new(
        row: &'record AttributeRow<'record>,
        ordinal: usize,
        value: &'record str,
        origin: &AttributeValueOrigin,
    ) -> Self {
        Self {
            fact_order: row.fact_order,
            fact_id: &row.fact.key,
            origin: origin.clone(),
            value_id: format!("{}:{ordinal}", origin.container_id),
            ordinal: ordinal as u64,
            value,
        }
    }
}
