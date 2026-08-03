use crate::protocol::Span as SourceSpan;
use serde::{Deserialize, Serialize};

/// Identity and source location of one declared method.
#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct MethodIdentity {
    pub name: String,
    pub span: SourceSpan,
    #[serde(default)]
    pub source: String,
    #[serde(default)]
    pub region: usize,
    #[serde(default = "method_kind")]
    pub kind: String,
    #[serde(default = "public_visibility")]
    pub visibility: String,
}

fn public_visibility() -> String {
    "public".to_string()
}

fn method_kind() -> String {
    "method".to_string()
}
