use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct ClassShape {
    #[serde(default)]
    pub has_instance_fields: bool,
    #[serde(default)]
    pub field_count: usize,
    #[serde(default)]
    pub has_inherited_fields: bool,
    #[serde(default)]
    pub direct_subclasses: Vec<String>,
    #[serde(default)]
    pub descendant_count: usize,
    #[serde(default)]
    pub is_instantiated: bool,
    #[serde(default)]
    pub is_exported: bool,
}
