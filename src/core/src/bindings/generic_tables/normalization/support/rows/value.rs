use super::super::scalar::ScalarValue;

mod location;

pub(crate) use location::{ValueContainer, ValueLocation};

pub(crate) struct ValueRow {
    pub(crate) fact_order: u64,
    pub(crate) fact_id: String,
    pub(crate) location: ValueLocation,
    pub(crate) value: Option<ScalarValue>,
}
