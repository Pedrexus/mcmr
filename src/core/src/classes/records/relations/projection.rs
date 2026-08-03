use crate::protocol::Span as SourceSpan;
use serde::{Deserialize, Serialize};

/// One structure that repeats attributes read from the same root.
#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct AttributeProjectionRecord {
    pub root: String,
    pub span: SourceSpan,
    #[serde(default)]
    pub attribute_names: Vec<String>,
    #[serde(default)]
    pub output_keys: Vec<String>,
}
