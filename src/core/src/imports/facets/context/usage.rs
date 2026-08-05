use crate::protocol::Node;
use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct ImportUsage {
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub(crate) references: Vec<Node>,
    #[serde(default, skip_serializing_if = "is_zero")]
    pub(crate) relative_level: usize,
    #[serde(default, skip_serializing_if = "is_zero")]
    pub(crate) reference_count: usize,
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub(crate) has_qualifying_use: bool,
}

fn is_zero(value: &usize) -> bool {
    *value == 0
}
