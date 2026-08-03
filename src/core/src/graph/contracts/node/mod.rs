use super::{
    datatype_kind::DatatypeKind, language::Language, node_kind::NodeKind, visibility::Visibility,
};
use serde::Serialize;
use std::ops::{Deref, DerefMut};

pub mod identity;
pub mod location;
pub mod parameter;
pub mod role;
pub mod signature;

use identity::NodeIdentity;

#[derive(Clone, Debug, Serialize)]
pub struct Node {
    #[serde(flatten)]
    identity: NodeIdentity,
}

impl Node {
    /// Declare one graph node with neutral optional language evidence.
    pub fn new(
        id: String,
        kind: NodeKind,
        language: Option<Language>,
        visibility: Visibility,
        qualname: String,
    ) -> Self {
        Self {
            identity: NodeIdentity {
                id,
                kind,
                language,
                visibility,
                qualname,
                location: Default::default(),
            },
        }
    }

    /// Mark a class node with the exact role its language frontend parsed.
    pub fn datatype(mut self, kind: DatatypeKind) -> Self {
        self.is_abstract = kind == DatatypeKind::Contract;
        self.is_enum = kind == DatatypeKind::Enumeration;
        self
    }
}

impl Deref for Node {
    type Target = NodeIdentity;

    fn deref(&self) -> &Self::Target {
        &self.identity
    }
}

impl DerefMut for Node {
    fn deref_mut(&mut self) -> &mut Self::Target {
        &mut self.identity
    }
}
