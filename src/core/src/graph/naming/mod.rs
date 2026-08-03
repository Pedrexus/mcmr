use super::contracts::Language;
use crate::discovery::{Crates, Document, Packages};
use std::collections::BTreeSet;

/// What every file in the repository calls itself, in the naming rule of its own language.
pub(crate) struct Naming {
    packages: Packages,
    crates: Crates,
}

impl Naming {
    pub(crate) fn of(root: &str, documents: &[Document]) -> Self {
        Self {
            packages: Packages::of(documents),
            crates: Crates::of(std::path::Path::new(root), documents),
        }
    }

    /// Return the language and module name declared by one path.
    ///
    /// Native and TypeScript files use their suffix-free paths. Python packages and Rust crates
    /// use the naming models already derived from the repository.
    pub(crate) fn module(&self, relative: &str) -> Option<(Language, String)> {
        let language = Language::of(relative)?;
        let stem = relative
            .rsplit_once('.')
            .map(|(stem, _)| stem)
            .unwrap_or(relative);
        let module = match language {
            Language::Python => self.packages.module_name(relative),
            Language::Rust => self.crates.module_name(relative),
            Language::TypeScript => stem.to_string(),
            _ => stem.replace('/', "::"),
        };
        Some((language, module))
    }

    /// Return every TypeScript module path available to specifier resolution.
    pub(crate) fn typescript(&self, documents: &[Document]) -> BTreeSet<String> {
        documents
            .iter()
            .filter_map(|document| match self.module(&document.relative) {
                Some((Language::TypeScript, module)) => Some(module),
                _ => None,
            })
            .collect()
    }
}
