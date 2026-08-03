use serde::{Deserialize, Serialize};

/// One provider claim retained beside a call fact.
#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct EvidenceRecord {
    pub signal: String,
    pub detail: String,
    pub source: String,
    #[serde(default = "full_confidence")]
    pub confidence: f64,
}

fn full_confidence() -> f64 {
    1.0
}
