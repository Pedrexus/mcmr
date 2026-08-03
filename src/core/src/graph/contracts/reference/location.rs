use crate::protocol::Node;

/// Source location and import node attached to one graph reference.
pub struct ReferenceLocation {
    pub path: String,
    pub line: usize,
    pub module_node: Option<Node>,
}
