use crate::protocol::Span as SourceSpan;
use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct ClassIdentity {
    pub name: String,
    pub path: String,
    pub span: SourceSpan,
    #[serde(default)]
    pub is_test: bool,
    #[serde(default)]
    pub source: String,
    #[serde(default = "module_scope")]
    pub scope: String,
    #[serde(default = "public_visibility")]
    pub visibility: String,
}

fn module_scope() -> String {
    "module".to_string()
}

fn public_visibility() -> String {
    "public".to_string()
}
