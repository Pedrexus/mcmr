use serde::{Deserialize, Serialize};

/// One explicit key and value held by a literal mapping expression.
#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct MappingEntry<T> {
    pub key: String,
    pub value: T,
}
