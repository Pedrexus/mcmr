use super::super::parameter_kind::ParameterKind;
use super::role::NodeRole;
use serde::Serialize;
use std::ops::{Deref, DerefMut};

#[derive(Clone, Debug, Default, Serialize)]
pub struct NodeParameter {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub ordinal: Option<usize>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub parameter_kind: Option<ParameterKind>,
    #[serde(skip_serializing_if = "std::ops::Not::not")]
    pub has_default: bool,
    #[serde(flatten)]
    pub role: NodeRole,
}

impl Deref for NodeParameter {
    type Target = NodeRole;

    fn deref(&self) -> &Self::Target {
        &self.role
    }
}

impl DerefMut for NodeParameter {
    fn deref_mut(&mut self) -> &mut Self::Target {
        &mut self.role
    }
}
