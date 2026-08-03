use super::access::AttributeAccess;
use serde::Serialize;
use serde_json::Value;

/// One file and every attribute access it performs.
#[derive(Clone, Debug, Serialize)]
pub struct AttributeAccessRecord {
    pub key: String,
    pub span: crate::protocol::Span,
    pub language: String,
    pub accesses: Vec<AttributeAccess>,
}

impl AttributeAccessRecord {
    /// Serialize one typed provider record for the independent JSON protocol.
    pub fn into_json(self) -> Value {
        serde_json::to_value(self).expect("a typed attribute access record must serialize")
    }
}
