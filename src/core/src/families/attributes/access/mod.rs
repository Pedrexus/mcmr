use serde::Serialize;

mod receiver;

pub use receiver::ReceiverEvidence;

/// One member access with its resolved receiver evidence.
#[derive(Clone, Debug, Serialize)]
pub struct AttributeAccess {
    pub name: String,
    pub visibility: String,
    pub is_inside_owning_class: bool,
    pub is_protocol_name: bool,
    #[serde(flatten)]
    pub receiver: ReceiverEvidence,
    pub node: crate::protocol::Node,
}
