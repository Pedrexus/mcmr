use super::super::method::MethodRecord;
use serde::{Deserialize, Serialize};

#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct ClassDeclaration {
    #[serde(default)]
    pub direct_bases: Vec<String>,
    #[serde(default)]
    pub is_protocol: bool,
    #[serde(default)]
    pub decorators: Vec<String>,
    #[serde(default)]
    pub class_keywords: Vec<String>,
    #[serde(default)]
    pub methods: Vec<MethodRecord>,
    #[serde(default)]
    pub has_explicit_registry_name: bool,
    #[serde(default)]
    pub states_model_configuration: bool,
}
