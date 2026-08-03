use serde::{Deserialize, Serialize};
use serde_json::Value;

mod facets;

pub use facets::{ImportContext, ImportIdentity, ImportOwnership, ImportShape};

/// One imported binding in the exact provider shape shared by every frontend.
#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct ImportBindingRecord {
    #[serde(flatten)]
    pub identity: ImportIdentity,
    #[serde(flatten)]
    pub context: ImportContext,
    #[serde(flatten)]
    pub ownership: ImportOwnership,
    #[serde(flatten)]
    pub shape: ImportShape,
}

impl ImportBindingRecord {
    /// Decode one frontend record at the typed table boundary.
    pub fn from_json(value: Value) -> Result<Self, String> {
        serde_json::from_value(value)
            .map_err(|failure| format!("an ImportBindingFact is invalid: {failure}"))
    }

    /// Serialize one typed record for exact compatibility parity.
    pub fn into_json(self) -> Value {
        serde_json::to_value(self).expect("a typed import binding record must serialize")
    }
}
