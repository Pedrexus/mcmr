use super::super::scalar::{ScalarKey, ScalarValue};
use std::collections::HashMap;

pub(crate) struct RecordRow {
    pub(crate) fact_order: u64,
    pub(crate) fact_id: String,
    pub(crate) relation: String,
    pub(crate) parent_id: String,
    pub(crate) record_id: String,
    pub(crate) ordinal: u64,
    pub(crate) scalars: HashMap<ScalarKey, ScalarValue>,
}
