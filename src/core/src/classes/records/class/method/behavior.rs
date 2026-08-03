use serde::{Deserialize, Serialize};

/// Receiver behavior stated by one declared method.
#[derive(Clone, Debug, Default, Deserialize, Serialize)]
pub struct MethodBehavior {
    #[serde(default)]
    pub is_protocol_name: bool,
    #[serde(default)]
    pub reads_receiver: bool,
    #[serde(default)]
    pub reads_receiver_state: bool,
}
