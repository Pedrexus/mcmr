use crate::families::{AttributeAccess, AttributeAccessRecord};

pub(super) struct AttributeRow<'record> {
    pub(super) fact_order: u64,
    pub(super) fact: &'record AttributeAccessRecord,
    pub(super) ordinal: u64,
    pub(super) record_id: String,
    pub(super) access: &'record AttributeAccess,
}
