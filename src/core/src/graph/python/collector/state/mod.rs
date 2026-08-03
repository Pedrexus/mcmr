use crate::graph::contracts::{Edge, Node, Reference};
use std::collections::BTreeMap;

/// Graph rows accumulated while one Python module is visited.
#[derive(Default)]
pub(super) struct GraphState {
    pub(super) nodes: Vec<Node>,
    pub(super) edges: Vec<Edge>,
    pub(super) references: Vec<Reference>,
    pub(super) export_references: Vec<Reference>,
    pub(super) aliases: BTreeMap<String, String>,
}
