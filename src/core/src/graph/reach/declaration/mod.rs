use super::counts::DeclarationCounts;
use crate::graph::contracts::Visibility;
use crate::protocol::Span;
use serde::Serialize;
use std::ops::Deref;

#[derive(Debug, Serialize)]
pub struct Declaration {
    pub qualname: String,
    pub kind: String,
    pub span: Span,
    pub is_module_scope: bool,
    pub is_decorated: bool,
    pub visibility: Visibility,
    #[serde(flatten)]
    pub(super) counts: DeclarationCounts,
}

impl Deref for Declaration {
    type Target = DeclarationCounts;

    fn deref(&self) -> &Self::Target {
        &self.counts
    }
}
