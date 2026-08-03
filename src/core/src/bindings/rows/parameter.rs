pub(in crate::bindings) struct ParameterRow<'record, Value> {
    pub(in crate::bindings) function_id: &'record str,
    pub(in crate::bindings) ordinal: u64,
    pub(in crate::bindings) parameter: &'record Value,
}
