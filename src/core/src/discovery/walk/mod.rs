use crate::protocol::{RepositoryPath, Request};
use std::collections::BTreeMap;
use std::hash::{DefaultHasher, Hash, Hasher};
use std::path::Path;
use std::process::Command;
use walkdir::{DirEntry, IntoIter, WalkDir};

pub use records::{Directory, Document, Inventory};
pub use scope::Scope;

mod records;
mod retention;
mod scope;

use retention::Retention;

/// Walk one root, reading every source file and recording every directory the walk scanned.
pub fn collect(request: &Request, scope: &Scope) -> Result<Inventory, String> {
    DiscoveryWalk::new(request, scope).collect()
}

struct DiscoveryWalk<'a> {
    request: &'a Request,
    scope: &'a Scope,
    root: &'a Path,
    documents: Vec<Document>,
    guides: Vec<Document>,
    directories: BTreeMap<String, Directory>,
    fingerprint: DefaultHasher,
}

impl<'a> DiscoveryWalk<'a> {
    fn new(request: &'a Request, scope: &'a Scope) -> Self {
        let mut fingerprint = DefaultHasher::new();
        request.suffixes.hash(&mut fingerprint);
        Self {
            request,
            scope,
            root: Path::new(&request.root),
            documents: Vec::new(),
            guides: Vec::new(),
            directories: BTreeMap::new(),
            fingerprint,
        }
    }

    fn collect(mut self) -> Result<Inventory, String> {
        let mut walker = WalkDir::new(self.root).into_iter();
        while let Some(found) = walker.next() {
            let entry =
                found.map_err(|failure| format!("repository discovery failed: {failure}"))?;
            self.visit(entry, &mut walker)?;
        }
        self.hash_head();
        self.documents
            .sort_by(|left, right| left.relative.cmp(&right.relative));
        self.guides
            .sort_by(|left, right| left.relative.cmp(&right.relative));
        Ok(Inventory {
            documents: self.documents,
            guides: self.guides,
            directories: self.directories.into_values().collect(),
            fingerprint: format!("{:016x}", self.fingerprint.finish()),
        })
    }

    fn hash_configuration(&mut self, entry: &DirEntry, relative: &str) -> Result<(), String> {
        std::fs::read(entry.path())
            .map_err(|failure| {
                format!("configuration file {relative} could not be read: {failure}")
            })?
            .hash(&mut self.fingerprint);
        Ok(())
    }

    fn hash_entry(&mut self, entry: &DirEntry, relative: &str) -> Result<(), String> {
        relative.hash(&mut self.fingerprint);
        entry.file_type().is_dir().hash(&mut self.fingerprint);
        if entry.file_type().is_file() {
            let metadata = entry.metadata().map_err(|failure| {
                format!("source file {relative} metadata could not be read: {failure}")
            })?;
            metadata.len().hash(&mut self.fingerprint);
            metadata
                .modified()
                .ok()
                .and_then(|modified| modified.duration_since(std::time::UNIX_EPOCH).ok())
                .map(|age| age.as_nanos())
                .hash(&mut self.fingerprint);
        }
        Ok(())
    }

    fn hash_head(&mut self) {
        if let Ok(head) = Command::new("git")
            .args(["-C", &self.request.root, "rev-parse", "HEAD"])
            .output()
            && head.status.success()
        {
            head.stdout.hash(&mut self.fingerprint);
        }
    }

    fn read(&mut self, entry: &DirEntry, relative: String) -> Result<Document, String> {
        let source = std::fs::read_to_string(entry.path()).map_err(|failure| {
            format!("source file {relative} could not be read as UTF-8: {failure}")
        })?;
        source.hash(&mut self.fingerprint);
        Ok(Document { relative, source })
    }

    fn record_directory(&mut self, relative: &str, retention: Retention, walker: &mut IntoIter) {
        match retention {
            Retention::Removed => walker.skip_current_dir(),
            Retention::Retained => {
                self.directories
                    .entry(relative.to_string())
                    .or_default()
                    .relative = relative.to_string();
            }
        }
    }

    fn record_parent(&mut self, entry: &DirEntry, relative: &str, retention: Retention) {
        let is_directory = entry.file_type().is_dir();
        let retained = retention == Retention::Retained;
        let is_source = !is_directory && self.scope.holds(relative);
        let parent = self
            .directories
            .entry(directory_of(relative).to_string())
            .or_default();
        let is_package_initializer = relative.rsplit('/').next() == Some("__init__.py");
        parent.entry_count += usize::from(retained);
        parent.direct_file_count +=
            usize::from(!is_directory && retained && !is_package_initializer);
        if is_directory && retained {
            parent.direct_directory_count += 1;
            parent.only_child_directory = match parent.direct_directory_count {
                1 => relative.rsplit('/').next().map(str::to_string),
                _ => None,
            };
        }
        parent.direct_module_count += usize::from(is_source && !is_package_initializer);
    }

    fn store_entry(
        &mut self,
        entry: DirEntry,
        relative: String,
        retention: Retention,
    ) -> Result<(), String> {
        let is_directory = entry.file_type().is_dir();
        let retained = retention == Retention::Retained;
        let is_source = !is_directory && self.scope.holds(&relative);
        let is_guide = !is_directory && retained && is_guidance(&relative);
        if is_source {
            let document = self.read(&entry, relative)?;
            self.documents.push(document);
        } else if is_guide {
            let document = self.read(&entry, relative)?;
            self.guides.push(document);
        } else if !is_directory && retained && is_configuration(&relative) {
            self.hash_configuration(&entry, &relative)?;
        }
        Ok(())
    }

    fn visit(&mut self, entry: DirEntry, walker: &mut IntoIter) -> Result<(), String> {
        let is_directory = entry.file_type().is_dir();
        if !is_directory && !entry.file_type().is_file() {
            return Ok(());
        }
        let relative = RepositoryPath::new(entry.path()).relative_to(self.root, "discovered")?;
        let retention = match is_directory {
            true if self.scope.excludes_directory(&relative) => Retention::Removed,
            false if self.scope.excludes(&relative) => Retention::Removed,
            _ => Retention::Retained,
        };
        if is_directory {
            self.record_directory(&relative, retention, walker);
        }
        if relative.is_empty() {
            return Ok(());
        }
        if retention == Retention::Retained {
            self.hash_entry(&entry, &relative)?;
        }
        self.record_parent(&entry, &relative, retention);
        self.store_entry(entry, relative, retention)
    }
}

fn is_guidance(relative: &str) -> bool {
    [".md", ".rst", ".txt"]
        .iter()
        .any(|suffix| relative.ends_with(suffix))
}

fn is_configuration(relative: &str) -> bool {
    relative.ends_with("Cargo.toml")
        || relative.ends_with("package.json")
        || relative.ends_with("pyproject.toml")
        || relative.ends_with("chefe.toml")
        || relative.ends_with("tsconfig.json")
        || relative.ends_with("jsconfig.json")
}

fn directory_of(path: &str) -> &str {
    path.rsplit_once('/').map(|(head, _)| head).unwrap_or("")
}
