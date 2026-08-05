use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct ClassRelations {
    #[serde(default)]
    pub only_cross_module_reference_is_subclass: bool,
    #[serde(default)]
    pub is_pass_through_layer: bool,
    #[serde(default)]
    pub base_is_removable_overlap: bool,
    #[serde(default)]
    pub has_redundant_direct_base: bool,
    #[serde(default)]
    pub has_noncooperative_concrete_collision: bool,
    #[serde(default)]
    pub duplicate_component_alias_count: usize,
}
