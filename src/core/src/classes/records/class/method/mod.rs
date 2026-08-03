use serde::{Deserialize, Serialize};

mod behavior;
mod identity;

pub use behavior::MethodBehavior;
pub use identity::MethodIdentity;

/// One directly declared method and the ordering evidence attached to it.
#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct MethodRecord {
    #[serde(flatten)]
    pub identity: MethodIdentity,
    #[serde(default)]
    pub decorators: Vec<String>,
    #[serde(flatten)]
    pub behavior: MethodBehavior,
    #[serde(default)]
    pub owner_qualified_calls: Vec<String>,
}
