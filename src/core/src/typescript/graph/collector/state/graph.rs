use crate::graph::{Edge, Node, Reference};
use std::collections::BTreeSet;

/// Graph rows and declared identities accumulated during collection.
#[derive(Default)]
pub(in crate::typescript::graph::collector) struct GraphState {
    pub(in crate::typescript::graph::collector) nodes: Vec<Node>,
    pub(in crate::typescript::graph::collector) edges: Vec<Edge>,
    pub(in crate::typescript::graph::collector) references: Vec<Reference>,
    pub(in crate::typescript::graph::collector) placed: BTreeSet<String>,
}
