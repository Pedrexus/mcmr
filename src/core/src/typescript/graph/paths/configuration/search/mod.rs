use super::chain::ConfigurationChain;
use super::table::Table;
use crate::discovery::Scope;
use crate::typescript::graph::paths::support::parent_of;
use std::collections::BTreeSet;
use std::path::{Path, PathBuf};

pub(super) struct ConfigurationSearch {
    root: PathBuf,
    ignored: Scope,
    visited: BTreeSet<String>,
}

impl ConfigurationSearch {
    pub(super) fn new(root: &Path) -> Self {
        Self {
            root: root.to_owned(),
            ignored: Scope::of(root, &[]),
            visited: BTreeSet::new(),
        }
    }

    pub(super) fn tables(&mut self, modules: &BTreeSet<String>) -> Result<Vec<Table>, String> {
        let mut tables = Vec::new();
        for module in modules {
            self.extend_tables(module, &mut tables)?;
        }
        tables.sort_by_key(|table| std::cmp::Reverse(table.directory.len()));
        Ok(tables)
    }

    fn extend_tables(&mut self, module: &str, tables: &mut Vec<Table>) -> Result<(), String> {
        let mut directory = parent_of(module).to_owned();
        loop {
            self.push_table(&directory, tables)?;
            if directory.is_empty() {
                return Ok(());
            }
            directory = parent_of(&directory).to_owned();
        }
    }

    fn push_table(&mut self, directory: &str, tables: &mut Vec<Table>) -> Result<(), String> {
        if !self.visited.insert(directory.to_owned()) {
            return Ok(());
        }
        let Some(mappings) =
            ConfigurationChain::new(&self.root, &self.ignored).mappings(directory)?
        else {
            return Ok(());
        };
        tables.push(Table {
            directory: directory.to_owned(),
            mappings,
        });
        Ok(())
    }
}
