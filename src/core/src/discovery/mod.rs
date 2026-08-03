use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};
use std::path::Path;

mod contracts;
mod walk;

use contracts::{CrateRoot, PathPrefix};
pub use contracts::{Crates, Packages, SourceRoots};
pub use walk::{Directory, Document, Inventory, Scope, collect};

#[cfg(test)]
use crate::protocol::Request;

/// One fact per directory the walk met, stating what it holds and where it sits.
///
/// The family carries no language, because a directory holding Python beside Rust belongs to
/// neither and the graph already identifies one as a path rather than under a language.
pub fn directories(
    directories: &[Directory],
    roots: &SourceRoots,
    catalogs: &BTreeSet<String>,
) -> Vec<Value> {
    directories
        .iter()
        .map(|directory| {
            let label = match directory.relative.is_empty() {
                true => ".",
                false => &directory.relative,
            };
            json!({
                "key": format!("directory:{label}"),
                "span": {"path": label},
                "entry_count": directory.entry_count,
                "source_depth": roots.depth(&directory.relative),
                "direct_file_count": directory.direct_file_count,
                "direct_directory_count": directory.direct_directory_count,
                "only_child_directory": directory.only_child_directory,
                "direct_module_count": directory.direct_module_count,
                "is_definition_catalog": catalogs.contains(&directory.relative),
            })
        })
        .collect()
}

/// The directories whose every module declares exactly one thing.
///
/// A folder holding one class or one rule per file is wide because that is what it is for, so the
/// rule counting modules exempts it. Whether a module declares one thing is what every frontend
/// already answered in `ModuleFact`, so this reads that answer rather than parsing a second time.
/// A package initializer is left out, since it states what the directory is rather than adding
/// something a reader has to choose between.
pub fn definition_catalogs(modules: &[Value]) -> BTreeSet<String> {
    let mut declared: BTreeMap<String, Vec<u64>> = BTreeMap::new();
    for module in modules {
        if module["is_package_initializer"]
            .as_bool()
            .expect("ModuleFact.is_package_initializer must be Boolean")
        {
            continue;
        }
        let path = module["span"]["path"]
            .as_str()
            .expect("ModuleFact.span.path must be text");
        let count = module["class_count"]
            .as_u64()
            .expect("ModuleFact.class_count must be unsigned")
            + module["function_count"]
                .as_u64()
                .expect("ModuleFact.function_count must be unsigned");
        declared
            .entry(directory_of(path).to_string())
            .or_default()
            .push(count);
    }
    declared
        .into_iter()
        .filter(|(_, counts)| counts.iter().all(|count| *count == 1))
        .map(|(directory, _)| directory)
        .collect()
}

/// The import roots of one repository, which decide what every module is called.
///
/// Python names regular packages from `__init__.py` and joins namespace portions with a package of
/// the same name under another import root. Reading both shapes from the tree keeps split source
/// roots, ordinary `src` layouts, and bare scripts naming themselves the way Python names them.
impl Packages {
    pub fn of(documents: &[Document]) -> Self {
        let regular: BTreeSet<String> = documents
            .iter()
            .filter(|document| document.relative.ends_with("/__init__.py"))
            .map(|document| directory_of(&document.relative).to_string())
            .collect();
        let names: BTreeSet<String> = regular
            .iter()
            .filter(|package| !has_package_ancestor(package, &regular))
            .filter_map(|package| package.rsplit('/').next())
            .map(str::to_string)
            .collect();
        let mut directories = regular;
        for document in documents {
            let mut candidate = directory_of(&document.relative);
            while !candidate.is_empty() {
                let candidate_name = candidate.rsplit('/').next().unwrap_or_default();
                let holds_same_named_package = directories.iter().any(|package| {
                    candidate.prefixes(package)
                        && package.rsplit('/').next() == Some(candidate_name)
                });
                if names.contains(candidate_name) && !holds_same_named_package {
                    directories.insert(candidate.to_string());
                }
                candidate = directory_of(candidate);
            }
        }
        Self { directories }
    }

    /// Return the dotted module name one repository-relative path declares.
    pub fn module_name(&self, relative: &str) -> String {
        let root = self
            .roots()
            .into_iter()
            .filter(|root| !root.is_empty() && root.prefixes(relative))
            .max_by_key(String::len);
        let inside = root
            .as_deref()
            .map(|root| relative.trim_start_matches(root).trim_start_matches('/'))
            .unwrap_or(relative);
        let trimmed = inside
            .strip_suffix(".pyi")
            .or_else(|| inside.strip_suffix(".py"))
            .unwrap_or(inside);
        let trimmed = trimmed.strip_suffix("/__init__").unwrap_or(trimmed);
        trimmed
            .split('/')
            .filter(|part| !part.is_empty())
            .collect::<Vec<_>>()
            .join(".")
    }

    /// Return every directory the import system starts naming a package chain from.
    ///
    /// The root is the first ancestor of a package that is not itself a package, which is exactly
    /// the boundary `module_name` stops walking up at, so a `src` layout, a nested package, and a
    /// flat layout at the repository root all report the directory their imports are written
    /// against.
    pub fn roots(&self) -> BTreeSet<String> {
        package_roots(&self.directories)
    }
}

fn has_package_ancestor(package: &str, regular: &BTreeSet<String>) -> bool {
    let mut ancestor = directory_of(package);
    while !ancestor.is_empty() {
        if regular.contains(ancestor) {
            return true;
        }
        ancestor = directory_of(ancestor);
    }
    false
}

fn package_roots(directories: &BTreeSet<String>) -> BTreeSet<String> {
    directories
        .iter()
        .filter(|package| !has_package_ancestor(package, directories))
        .map(|package| directory_of(package).to_string())
        .collect()
}

fn directory_of(path: &str) -> &str {
    path.rsplit_once('/').map(|(head, _)| head).unwrap_or("")
}

/// The crate roots of one repository, which decide what every Rust module is called.
///
/// Rust names a module by where it sits under the crate root, and the root is the directory whose
/// `src` holds a `lib.rs` or a `main.rs`. The crate is named by that directory, not by the package
/// name in the manifest, since two crates in one repository are told apart by where they live and
/// a manifest is not always a file this kernel was asked to read.
impl Crates {
    pub fn of(root: &Path, documents: &[Document]) -> Self {
        let repository_name = root
            .canonicalize()
            .unwrap_or_else(|_| root.to_path_buf())
            .file_name()
            .and_then(|name| name.to_str())
            .unwrap_or("crate")
            .to_string();
        Self {
            roots: documents
                .iter()
                .filter_map(|document| {
                    let directory = directory_of(&document.relative);
                    let name = document.relative.rsplit('/').next().unwrap_or_default();
                    let is_root = matches!(name, "lib.rs" | "main.rs") && ends_in_src(directory);
                    is_root.then(|| {
                        let prefix = directory.trim_end_matches("src").to_string();
                        let name = prefix
                            .trim_end_matches('/')
                            .rsplit('/')
                            .next()
                            .filter(|name| !name.is_empty())
                            .unwrap_or(&repository_name)
                            .to_string();
                        CrateRoot { prefix, name }
                    })
                })
                .collect(),
        }
    }

    /// Return the path-separated module name one repository-relative path declares.
    pub fn module_name(&self, relative: &str) -> String {
        let root = self
            .roots
            .iter()
            .filter(|root| relative.starts_with(root.prefix.as_str()))
            .max_by_key(|root| root.prefix.len());
        let Some(root) = root else {
            return relative
                .strip_suffix(".rs")
                .unwrap_or(relative)
                .replace('/', "::");
        };
        let inside = relative.trim_start_matches(root.prefix.as_str());
        let trimmed = inside
            .trim_start_matches("src/")
            .strip_suffix(".rs")
            .unwrap_or(inside);
        let parts: Vec<&str> = trimmed
            .split('/')
            .filter(|part| !part.is_empty() && !matches!(*part, "lib" | "main" | "mod"))
            .collect();
        std::iter::once(root.name.as_str())
            .chain(parts)
            .collect::<Vec<_>>()
            .join("::")
    }
}

fn ends_in_src(directory: &str) -> bool {
    directory == "src" || directory.ends_with("/src")
}

/// The directories this kernel starts naming modules from, which is what depth is measured against.
///
/// A path is only deep relative to where its language begins counting. Python begins at the first
/// ancestor that is not a package, Rust begins at the `src` beside a crate root, and every other
/// layout this kernel reads spells that boundary `src` as well, so those two answers are the whole
/// set. Reading them off the tree is what keeps the measure from needing a setting nobody updates.
impl SourceRoots {
    pub fn of(directories: &[Directory], packages: &Packages) -> Self {
        Self {
            directories: directories
                .iter()
                .map(|directory| directory.relative.clone())
                .filter(|relative| ends_in_src(relative))
                .chain(packages.roots())
                .collect(),
        }
    }

    /// Return how many directory levels one directory sits below the source root above it.
    pub fn depth(&self, directory: &str) -> usize {
        let inside = self
            .directories
            .iter()
            .filter(|root| root.prefixes(directory))
            .max_by_key(|root| root.len())
            .and_then(|root| directory.strip_prefix(root.as_str()))
            .unwrap_or(directory);
        inside.split('/').filter(|part| !part.is_empty()).count()
    }
}

#[cfg(test)]
mod tests;
