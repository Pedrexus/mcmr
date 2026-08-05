use crate::protocol::Node;
use serde::{Deserialize, Serialize};
use std::ops::{Deref, DerefMut};

mod usage;

use usage::ImportUsage;

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
    #[serde(flatten)]
    pub usage: ImportUsage,
}

impl Deref for ImportContext {
    type Target = ImportUsage;

    fn deref(&self) -> &Self::Target {
        &self.usage
    }
}

impl DerefMut for ImportContext {
    fn deref_mut(&mut self) -> &mut Self::Target {
        &mut self.usage
    }
}
