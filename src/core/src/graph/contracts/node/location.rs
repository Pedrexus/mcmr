use super::signature::NodeSignature;
use serde::Serialize;
use std::ops::{Deref, DerefMut};

#[derive(Clone, Debug, Default, Serialize)]
pub struct NodeLocation {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub path: Option<String>,
    #[serde(skip_serializing_if = "std::ops::Not::not")]
    pub is_package: bool,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub line: Option<usize>,
    #[serde(skip)]
    pub source: Option<String>,
    #[serde(flatten)]
    pub signature: NodeSignature,
}

impl Deref for NodeLocation {
    type Target = NodeSignature;

    fn deref(&self) -> &Self::Target {
        &self.signature
    }
}

impl DerefMut for NodeLocation {
    fn deref_mut(&mut self) -> &mut Self::Target {
        &mut self.signature
    }
}
