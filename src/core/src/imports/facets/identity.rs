use crate::calls::EvidenceRecord;
use crate::protocol::Span;
use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct ImportIdentity {
    pub key: String,
    pub span: Span,
    #[serde(default)]
    pub language: String,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub evidence: Vec<EvidenceRecord>,
    pub name: String,
    pub module: String,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub imported_name: String,
}
