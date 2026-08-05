use super::counts::DeclarationCounts;
use crate::graph::contracts::Visibility;
use serde::Serialize;
use std::ops::Deref;

mod context;
mod owner;

pub(crate) use context::DeclarationContext;
pub(crate) use owner::OwnerContract;

#[derive(Debug, Serialize)]
pub struct Declaration {
    pub qualname: String,
    pub kind: String,
    #[serde(flatten)]
    pub(crate) context: DeclarationContext,
    pub visibility: Visibility,
    #[serde(flatten)]
    pub(crate) owner: OwnerContract,
    #[serde(flatten)]
    pub(super) counts: DeclarationCounts,
}

impl Deref for Declaration {
    type Target = DeclarationCounts;

    fn deref(&self) -> &Self::Target {
        &self.counts
    }
}
