use super::super::mapping::Mapping;
use crate::typescript::graph::paths::names::JoinedPath;
use serde::Deserialize;
use std::collections::BTreeMap;

#[derive(Debug, Default, Deserialize)]
#[serde(default, rename_all = "camelCase")]
pub(super) struct CompilerOptions {
    base_url: Option<String>,
    paths: BTreeMap<String, Vec<String>>,
}

impl CompilerOptions {
    pub(super) fn mappings(&self, holder: &str) -> Result<Vec<Mapping>, String> {
        let base = JoinedPath {
            parent: holder,
            child: self.base_url.as_deref().unwrap_or("."),
        }
        .normalized();
        self.paths
            .iter()
            .map(|(pattern, targets)| Mapping::from_config(pattern, targets, &base))
            .collect()
    }
}
