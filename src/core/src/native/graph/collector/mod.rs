use crate::graph::{Edge, Language, Node, Reference};
use crate::source::Source;

/// Every definition and reference collected from one translation unit.
pub(super) struct Collector {
    pub(super) source: Source,
    pub(super) language: Language,
    pub(super) scopes: Vec<String>,
    pub(super) owners: Vec<String>,
    pub(super) nodes: Vec<Node>,
    pub(super) edges: Vec<Edge>,
    pub(super) references: Vec<Reference>,
}
