use crate::graph::contracts::{edge_kind::EdgeKind, resolution::Resolution};
use serde::Serialize;

#[derive(Clone, Debug, Serialize)]
pub struct Edge {
    pub source: String,
    pub target: String,
    pub kind: EdgeKind,
    pub path: String,
    pub line: usize,
    pub resolution: Resolution,
}
