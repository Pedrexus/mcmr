use super::reference::Reference;
use serde::Serialize;

/// One route and every other source location that names its path.
#[derive(Clone, Debug, Serialize)]
pub struct Route {
    pub method: String,
    pub path: String,
    pub framework: String,
    pub declared_in: String,
    pub line: usize,
    pub is_prefix_composed: bool,
    pub references: Vec<Reference>,
}
