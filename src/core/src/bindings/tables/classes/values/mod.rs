use super::core::{class_rows, method_rows};
use crate::bindings::frames::string_values::{StringValueColumns, selected_string_value_frame};
use crate::classes::ClassRecord;
use polars::prelude::*;

pub(super) use class::ClassValue;
pub(super) use method::MethodValue;

mod class;
mod method;

pub(super) fn class_value_frame(
    records: &[ClassRecord],
    field: ClassValue,
) -> PolarsResult<DataFrame> {
    selected_string_value_frame(
        StringValueColumns {
            id: "class_id",
            value: "value",
        },
        class_rows(records)
            .into_iter()
            .map(|row| (row.id, row.value)),
        |class| field.values(class),
    )
}

pub(super) fn method_value_frame(
    records: &[ClassRecord],
    field: MethodValue,
) -> PolarsResult<DataFrame> {
    selected_string_value_frame(
        StringValueColumns {
            id: "method_id",
            value: "value",
        },
        method_rows(records)
            .into_iter()
            .map(|row| (row.id, row.method)),
        |method| field.values(method),
    )
}
