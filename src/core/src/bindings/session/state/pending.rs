use serde_json::Value;

pub(in crate::bindings::session) struct PendingGenericTable {
    pub(in crate::bindings::session) rows: Vec<Value>,
    pub(in crate::bindings::session) schema: String,
}
