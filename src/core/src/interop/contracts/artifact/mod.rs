use super::mechanism::Mechanism;
use serde::Serialize;

mod reference;

pub(in crate::interop) use reference::Reference;

/// One artifact a repository declares in one language and reaches from another.
#[derive(Clone, Debug, Serialize)]
pub(crate) struct Artifact {
    pub name: String,
    pub mechanism: Mechanism,
    pub language: String,
    pub declared_in: String,
    pub referenced_by: Vec<Reference>,
}
