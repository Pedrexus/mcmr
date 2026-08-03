use super::super::{language::Language, node_kind::NodeKind, visibility::Visibility};
use super::location::NodeLocation;
use serde::Serialize;
use std::ops::{Deref, DerefMut};

#[derive(Clone, Debug, Serialize)]
pub struct NodeIdentity {
    pub id: String,
    pub kind: NodeKind,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub language: Option<Language>,
    pub visibility: Visibility,
    pub qualname: String,
    #[serde(flatten)]
    pub location: NodeLocation,
}

impl Deref for NodeIdentity {
    type Target = NodeLocation;

    fn deref(&self) -> &Self::Target {
        &self.location
    }
}

impl DerefMut for NodeIdentity {
    fn deref_mut(&mut self) -> &mut Self::Target {
        &mut self.location
    }
}
