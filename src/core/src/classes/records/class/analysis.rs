use serde::{Deserialize, Serialize};

mod declaration;
mod identity;
mod model;
mod relations;
mod shape;

pub use declaration::ClassDeclaration;
pub use identity::ClassIdentity;
pub use model::ClassModel;
pub use relations::ClassRelations;
pub use shape::ClassShape;

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
