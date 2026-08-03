use crate::calls::EvidenceRecord;
use crate::protocol::Span;
use serde::Serialize;

#[derive(Clone, Debug, Default, Serialize)]
pub struct FunctionIdentity {
    pub key: String,
    pub span: Span,
    pub language: String,
    pub is_test: bool,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub evidence: Vec<EvidenceRecord>,
    pub name: String,
    pub scope: String,
}
