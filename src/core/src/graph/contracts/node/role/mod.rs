use serde::Serialize;

#[derive(Clone, Debug, Default, Serialize)]
pub struct NodeRole {
    #[serde(skip_serializing_if = "std::ops::Not::not")]
    pub is_abstract: bool,
    #[serde(skip_serializing_if = "std::ops::Not::not")]
    pub is_enum: bool,
}
