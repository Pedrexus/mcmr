use serde::{Deserialize, Serialize};

mod facets;

pub use facets::{ClassDeclaration, ClassIdentity, ClassModel, ClassRelations, ClassShape};

/// One class and every closed-world property deterministic class rules read.
#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct ClassAnalysisRecord {
    #[serde(flatten)]
    pub identity: ClassIdentity,
    #[serde(flatten)]
    pub declaration: ClassDeclaration,
    #[serde(flatten)]
    pub shape: ClassShape,
    #[serde(flatten)]
    pub relations: ClassRelations,
    #[serde(flatten)]
    pub model: ClassModel,
}
