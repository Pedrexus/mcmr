use crate::calls::EvidenceRecord;
use crate::protocol::Span as SourceSpan;
use serde::{Deserialize, Serialize};
use serde_json::Value;

mod analysis;
mod collections;
mod method;

pub use analysis::ClassAnalysisRecord;
pub use collections::ClassRelations;
pub use method::{MethodBehavior, MethodIdentity, MethodRecord};

/// One graph-enriched class family ready for normalized table construction.
#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct ClassRecord {
    pub key: String,
    pub span: SourceSpan,
    pub language: String,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub evidence: Vec<EvidenceRecord>,
    #[serde(default)]
    pub classes: Vec<ClassAnalysisRecord>,
    #[serde(flatten)]
    pub relations: ClassRelations,
    #[serde(default)]
    pub has_approved_model_foundation_policy: bool,
}

impl ClassRecord {
    /// Decode one graph-enriched compatibility record at the typed table boundary.
    pub fn from_json(value: Value) -> Result<Self, String> {
        serde_json::from_value(value)
            .map_err(|failure| format!("a graph-enriched ClassFact is invalid: {failure}"))
    }

    /// Serialize one typed class record for exact compatibility parity.
    pub fn into_json(self) -> Value {
        serde_json::to_value(self).expect("a typed class record must serialize")
    }
}
