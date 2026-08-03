use crate::protocol::Node;
use serde::Serialize;

mod bypass;

pub use bypass::ExportBypass;

/// One explicitly published Python name and how often repository code uses that public route.
#[derive(Clone, Debug, Serialize)]
pub struct Export {
    pub module: String,
    pub name: String,
    pub target: String,
    pub path: String,
    pub nodes: Vec<Node>,
    pub consumer_count: usize,
    pub bypasses: Vec<ExportBypass>,
}
