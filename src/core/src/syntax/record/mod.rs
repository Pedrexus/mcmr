use crate::protocol::Span;
use serde::{Deserialize, Serialize};
use serde_json::Value;

/// One compact preorder syntax node with child indices into its owning record.
pub type PackedSyntaxRecord = (String, String, usize, usize, usize, usize, Vec<usize>);

/// One declaration syntax tree ready for normalized table construction.
#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct SyntaxRecord {
    pub key: String,
    pub span: Span,
    pub language: String,
    #[serde(default)]
    pub qualname: String,
    #[serde(default)]
    pub kind: String,
    #[serde(default)]
    pub source: String,
    #[serde(default)]
    pub nodes: Vec<PackedSyntaxRecord>,
}

impl SyntaxRecord {
    /// Decode one compact compatibility record at the typed table boundary.
    pub fn from_json(value: Value) -> Result<Self, String> {
        serde_json::from_value(value)
            .map_err(|failure| format!("a SyntaxFact is invalid: {failure}"))
    }

    /// Serialize one typed syntax record for exact compatibility parity.
    pub fn into_json(self) -> Value {
        serde_json::to_value(self).expect("a typed syntax record must serialize")
    }
}
