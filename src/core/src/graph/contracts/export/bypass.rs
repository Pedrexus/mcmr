use crate::protocol::Node;
use serde::Serialize;

/// One import that reaches a declaration beneath its shortest explicit package surface.
#[derive(Clone, Debug, Serialize)]
pub struct ExportBypass {
    pub path: String,
    pub line: usize,
    pub expression: String,
    pub module_node: Option<Node>,
    pub replacement_module: Option<String>,
    pub binding_count: usize,
    pub is_cycle_safe: bool,
}
