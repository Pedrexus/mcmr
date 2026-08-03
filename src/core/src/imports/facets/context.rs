use crate::protocol::Node;
use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct ImportContext {
    #[serde(default, skip_serializing_if = "String::is_empty")]
    pub importer_module: String,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub declaration: Option<Node>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub binding: Option<Node>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub module_node: Option<Node>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub references: Vec<Node>,
    #[serde(default, skip_serializing_if = "is_zero")]
    pub relative_level: usize,
    #[serde(default, skip_serializing_if = "is_zero")]
    pub reference_count: usize,
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub has_qualifying_use: bool,
}

fn is_zero(value: &usize) -> bool {
    *value == 0
}
