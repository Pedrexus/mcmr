use super::{edge_kind::EdgeKind, language::Language};

mod location;
mod resolution;

pub use location::ReferenceLocation;
pub use resolution::ReferenceResolution;

/// One reference awaiting the repository-wide resolution its own module cannot perform.
pub struct Reference {
    pub source: String,
    pub expression: String,
    pub language: Language,
    pub module: String,
    pub resolution: ReferenceResolution,
    pub kind: EdgeKind,
    pub location: ReferenceLocation,
}
