use super::mapping::MappingEntry;
use crate::protocol::Node;
use serde::{Deserialize, Serialize};

/// One expression attached to a call, including the nested producer tree.
#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct Expression {
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub text: String,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub qualified_name: String,
    #[serde(default = "none_literal", skip_serializing_if = "is_none_literal")]
    pub literal_kind: String,
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub resolved_type: String,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub arguments: Vec<Expression>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub entries: Vec<MappingEntry<Expression>>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub node: Option<Node>,
}

impl Expression {
    /// Start one source expression with neutral resolution and child evidence.
    pub fn new(text: String, node: Node) -> Self {
        Self {
            text,
            qualified_name: String::new(),
            literal_kind: none_literal(),
            resolved_type: String::new(),
            arguments: Vec::new(),
            entries: Vec::new(),
            node: Some(node),
        }
    }
}

fn none_literal() -> String {
    "none".to_string()
}

fn is_none_literal(value: &str) -> bool {
    value == "none"
}
