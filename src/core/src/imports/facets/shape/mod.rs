use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct ImportShape {
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub is_sole_binding: bool,
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub has_private_module_component: bool,
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub is_private_member: bool,
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub is_private_uppercase_constant: bool,
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub is_wildcard: bool,
}
