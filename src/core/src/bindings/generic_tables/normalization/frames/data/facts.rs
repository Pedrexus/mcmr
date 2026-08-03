use crate::bindings::generic_tables::normalization::support::rows::NormalizedRow;
use crate::bindings::generic_tables::normalization::support::{
    ColumnCatalog, FactRow, RecordRow, ScalarKey, ScalarValue,
};
use crate::bindings::generic_tables::schema::ScalarKind;
use polars::prelude::*;
use std::collections::HashMap;

pub(super) fn normalized_fact_columns(rows: &[impl NormalizedRow]) -> Result<Vec<Column>, String> {
    Ok(df![
        "fact_order" => rows.iter().map(NormalizedRow::fact_order).collect::<Vec<_>>(),
        "fact_id" => rows.iter().map(NormalizedRow::fact_id).collect::<Vec<_>>(),
    ]
    .map_err(|failure| failure.to_string())?
    .into_columns())
}

pub(crate) fn fact_frame(rows: &[FactRow], catalog: &ColumnCatalog) -> Result<DataFrame, String> {
    scalar_table(
        rows,
        catalog,
        fact_fixed_frame(rows)?,
        &[
            "fact_order",
            "fact_id",
            "path",
            "start_line",
            "start_column",
            "end_line",
            "end_column",
            "language",
        ],
        |row| &row.scalars,
    )
}

fn fact_fixed_frame(rows: &[FactRow]) -> Result<DataFrame, String> {
    df![
        "path" => rows.iter().map(|row| row.span.path.as_str()).collect::<Vec<_>>(),
        "start_line" => rows.iter().map(|row| row.span.start_line).collect::<Vec<_>>(),
        "start_column" => rows.iter().map(|row| row.span.start_column).collect::<Vec<_>>(),
        "end_line" => rows.iter().map(|row| row.span.end_line).collect::<Vec<_>>(),
        "end_column" => rows.iter().map(|row| row.span.end_column).collect::<Vec<_>>(),
        "language" => rows.iter().map(|row| row.language.as_deref()).collect::<Vec<_>>(),
    ]
    .map_err(|failure| failure.to_string())
}

pub(crate) fn record_frame(
    rows: &[RecordRow],
    catalog: &ColumnCatalog,
) -> Result<DataFrame, String> {
    scalar_table(
        rows,
        catalog,
        record_fixed_frame(rows)?,
        &[
            "fact_order",
            "fact_id",
            "relation",
            "parent_id",
            "record_id",
            "ordinal",
        ],
        |row| &row.scalars,
    )
}

fn record_fixed_frame(rows: &[RecordRow]) -> Result<DataFrame, String> {
    df![
        "relation" => rows.iter().map(|row| row.relation.as_str()).collect::<Vec<_>>(),
        "parent_id" => rows.iter().map(|row| row.parent_id.as_str()).collect::<Vec<_>>(),
        "record_id" => rows.iter().map(|row| row.record_id.as_str()).collect::<Vec<_>>(),
        "ordinal" => rows.iter().map(|row| row.ordinal).collect::<Vec<_>>(),
    ]
    .map_err(|failure| failure.to_string())
}

fn scalar_table<'a, Row: NormalizedRow>(
    rows: &'a [Row],
    catalog: &ColumnCatalog,
    fixed: DataFrame,
    reserved: &[&str],
    scalars: impl Fn(&'a Row) -> &'a HashMap<ScalarKey, ScalarValue> + Copy,
) -> Result<DataFrame, String> {
    let mut columns = normalized_fact_columns(rows)?;
    columns.extend(fixed.into_columns());
    append_scalar_columns(&mut columns, rows.iter().map(scalars), catalog, reserved);
    DataFrame::new(rows.len(), columns).map_err(|failure| failure.to_string())
}

macro_rules! scalar_column {
    ($name:expr, $rows:expr, $key:expr, $project:ident) => {
        Column::new(
            $name.into(),
            $rows
                .clone()
                .map(|row| row.get(&$key).and_then(ScalarValue::$project))
                .collect::<Vec<_>>(),
        )
    };
}

fn append_scalar_columns<'a>(
    columns: &mut Vec<Column>,
    rows: impl Iterator<Item = &'a HashMap<ScalarKey, ScalarValue>> + Clone,
    catalog: &ColumnCatalog,
    reserved: &[&str],
) {
    for (key, name) in catalog.columns(reserved) {
        let column = match key.kind {
            ScalarKind::Boolean => scalar_column!(name, rows, key, boolean),
            ScalarKind::Float => scalar_column!(name, rows, key, float),
            ScalarKind::Integer => scalar_column!(name, rows, key, integer),
            ScalarKind::String => scalar_column!(name, rows, key, text),
        };
        columns.push(column);
    }
}
