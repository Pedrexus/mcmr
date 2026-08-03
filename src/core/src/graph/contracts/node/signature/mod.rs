use super::parameter::NodeParameter;
use serde::Serialize;
use std::ops::{Deref, DerefMut};

#[derive(Clone, Debug, Default, Serialize)]
pub struct NodeSignature {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub annotation: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub return_annotation: Option<String>,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub decorators: Vec<String>,
    #[serde(skip_serializing_if = "std::ops::Not::not")]
    pub asynchronous: bool,
    #[serde(flatten)]
    pub parameter: NodeParameter,
}

impl Deref for NodeSignature {
    type Target = NodeParameter;

    fn deref(&self) -> &Self::Target {
        &self.parameter
    }
}

impl DerefMut for NodeSignature {
    fn deref_mut(&mut self) -> &mut Self::Target {
        &mut self.parameter
    }
}
