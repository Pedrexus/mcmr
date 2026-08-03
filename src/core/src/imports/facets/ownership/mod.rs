use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct ImportOwnership {
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub is_external: bool,
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub is_reexported: bool,
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub is_type_only: bool,
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub has_documented_side_effect: bool,
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub is_relative: bool,
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub is_project_owned: bool,
}
