use super::{edge::Edge, node::Node, reference::Reference};
use crate::protocol::Node as SourceNode;
use std::collections::{BTreeMap, BTreeSet};

/// Everything one file states about itself, which resolution then joins to the repository.
#[derive(Default)]
pub struct Stated {
    pub nodes: Vec<Node>,
    pub edges: Vec<Edge>,
    pub references: Vec<Reference>,
    pub export_references: Vec<Reference>,
    pub aliases: BTreeMap<String, String>,
    pub exports: BTreeSet<String>,
    pub export_nodes: BTreeMap<String, Vec<SourceNode>>,
}
