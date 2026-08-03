use super::support::{Located, package_of, without_suffix};
#[cfg(test)]
use chain::ConfigurationChain;
#[cfg(test)]
use mapping::Mapping;
use search::ConfigurationSearch;
use std::collections::BTreeSet;
use std::path::Path;
use table::Table;

pub use request::WrittenSpecifier;

mod chain;
mod mapping;
mod request;
mod search;
mod table;
mod targets;

/// Settle TypeScript imports through relative paths and inherited configuration mappings.
#[derive(Debug)]
pub struct Specifiers {
    modules: BTreeSet<String>,
    tables: Vec<Table>,
}

impl Specifiers {
    /// Read every configuration that governs a TypeScript file of this repository.
    pub fn of(root: &str, modules: BTreeSet<String>) -> Result<Self, String> {
        let tables = ConfigurationSearch::new(Path::new(root)).tables(&modules)?;
        Ok(Self { modules, tables })
    }

    /// Return where one specifier written in one file lands.
    pub fn locate(&self, specifier: WrittenSpecifier<'_>) -> Located {
        if specifier.value.starts_with('.') {
            return self.relative_location(&specifier);
        }
        self.mapped_location(&specifier)
            .unwrap_or_else(|| Located::Package(package_of(specifier.value)))
    }

    fn mapped_location(&self, specifier: &WrittenSpecifier<'_>) -> Option<Located> {
        for table in &self.tables {
            if !specifier.governed_by(&table.directory) {
                continue;
            }
            for mapping in &table.mappings {
                let Some(candidates) = mapping.apply(specifier.value) else {
                    continue;
                };
                if let Some(module) = candidates.values().find_map(|base| self.settle(base)) {
                    return Some(Located::Module(module));
                }
                return Some(Located::Unsettled(candidates.first));
            }
        }
        None
    }

    fn relative_location(&self, specifier: &WrittenSpecifier<'_>) -> Located {
        let written = specifier.relative_path();
        match self.settle(&written) {
            Some(module) => Located::Module(module),
            None => Located::Unsettled(written),
        }
    }

    /// Return the module one written path names, trying every file TypeScript would try.
    fn settle(&self, written: &str) -> Option<String> {
        let stem = without_suffix(written);
        [
            stem.to_string(),
            format!("{stem}.d"),
            format!("{stem}/index"),
            format!("{stem}/index.d"),
        ]
        .into_iter()
        .find(|candidate| self.modules.contains(candidate))
    }
}

/// Return the mappings the configuration in one directory states, across its `extends` chain.
///
/// A `paths` entry is written against the file that declares it, so each step of the chain
/// rewrites its own targets against its own directory before they join the table. A visited set
/// stops a configuration that extends itself without limiting a valid chain.
#[cfg(test)]
pub(in crate::typescript) fn mappings_at(
    root: &Path,
    directory: &str,
    ignored: &crate::discovery::Scope,
) -> Result<Option<Vec<Mapping>>, String> {
    ConfigurationChain::new(root, ignored).mappings(directory)
}
