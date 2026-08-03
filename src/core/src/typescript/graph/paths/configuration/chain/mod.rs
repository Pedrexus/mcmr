use super::super::json::read_config;
use super::mapping::Mapping;
use crate::discovery::Scope;
use crate::typescript::graph::paths::names::JoinedPath;
use config::TypeScriptConfig;
use std::collections::BTreeSet;
use std::path::Path;

mod config;
mod options;

pub(super) struct ConfigurationChain<'scope> {
    root: &'scope Path,
    ignored: &'scope Scope,
    visited: BTreeSet<String>,
}

impl<'scope> ConfigurationChain<'scope> {
    pub(super) fn new(root: &'scope Path, ignored: &'scope Scope) -> Self {
        Self {
            root,
            ignored,
            visited: BTreeSet::new(),
        }
    }

    pub(super) fn mappings(mut self, directory: &str) -> Result<Option<Vec<Mapping>>, String> {
        let Some(current) = self.first_configuration(directory)? else {
            return Ok(None);
        };
        self.collect_mappings(current).map(Some)
    }

    fn collect_mappings(&mut self, mut current: String) -> Result<Vec<Mapping>, String> {
        let mut mappings = Vec::new();
        while !self.ignored.excludes(&current) {
            self.remember(&current)?;
            let config: TypeScriptConfig = read_config(&self.root.join(&current))?;
            mappings.extend(config.mappings(&current)?);
            let Some(next) = config.next_path(&current)? else {
                break;
            };
            current = next;
        }
        Ok(mappings)
    }

    fn configuration_name(&self, directory: &str) -> Result<Option<&'static str>, String> {
        for candidate in ["tsconfig.json", "jsconfig.json"] {
            let relative = JoinedPath {
                parent: directory,
                child: candidate,
            }
            .render();
            let path = self.root.join(directory).join(candidate);
            if !self.ignored.excludes(&relative) && inspected(&path)? {
                return Ok(Some(candidate));
            }
        }
        Ok(None)
    }

    fn first_configuration(&self, directory: &str) -> Result<Option<String>, String> {
        Ok(self.configuration_name(directory)?.map(|name| {
            JoinedPath {
                parent: directory,
                child: name,
            }
            .render()
        }))
    }

    fn remember(&mut self, current: &str) -> Result<(), String> {
        if self.visited.insert(current.to_owned()) {
            return Ok(());
        }
        Err(format!(
            "{current} forms a circular TypeScript extends chain"
        ))
    }
}

fn inspected(path: &Path) -> Result<bool, String> {
    path.try_exists().map_err(|failure| {
        format!(
            "TypeScript configuration path {} could not be inspected: {failure}",
            path.display()
        )
    })
}
