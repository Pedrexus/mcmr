use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct ClassModel {
    #[serde(default)]
    pub is_declarative_model: bool,
    #[serde(default)]
    pub is_dataclass: bool,
    #[serde(default)]
    pub has_ordinary_behavior: bool,
    #[serde(default)]
    pub importing_modules: Vec<String>,
    #[serde(default)]
    pub proposed_model_destination: String,
    #[serde(default)]
    pub directly_inherits_pydantic_base_model: bool,
    #[serde(default)]
    pub inherits_approved_model_foundation: bool,
}
