use super::{edge::Edge, export::Export, node::Node};
use serde::Serialize;

/// The repository graph, with its nodes and every source site that relates them.
#[derive(Debug, Default, Serialize)]
pub struct Graph {
    pub nodes: Vec<Node>,
    pub edges: Vec<Edge>,
    #[serde(skip_serializing)]
    pub exports: Vec<Export>,
}
