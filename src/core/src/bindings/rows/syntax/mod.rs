mod bytes;
mod traversal;

pub(in crate::bindings) use bytes::SyntaxBytes;
pub(in crate::bindings) use traversal::NodeTraversal;

pub(in crate::bindings) struct SyntaxNodeRow<'record, Value> {
    pub(in crate::bindings) fact_order: u64,
    pub(in crate::bindings) fact_id: &'record str,
    pub(in crate::bindings) path: &'record str,
    pub(in crate::bindings) node: &'record Value,
    pub(in crate::bindings) traversal: NodeTraversal,
    pub(in crate::bindings) bytes: SyntaxBytes,
}
