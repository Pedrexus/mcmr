pub(in crate::bindings) struct MethodRow<'record, Value> {
    pub(in crate::bindings) id: String,
    pub(in crate::bindings) class_id: String,
    pub(in crate::bindings) ordinal: u64,
    pub(in crate::bindings) method: &'record Value,
}
