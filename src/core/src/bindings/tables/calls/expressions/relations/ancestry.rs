use super::ExpressionEdge;

pub(in crate::bindings::tables::calls::expressions) struct ExpressionAncestryRow {
    pub(in crate::bindings::tables::calls::expressions) call_id: String,
    pub(in crate::bindings::tables::calls::expressions) descendant_expression_id: String,
    pub(in crate::bindings::tables::calls::expressions) step: u64,
    pub(in crate::bindings::tables::calls::expressions) edge: ExpressionEdge,
}
