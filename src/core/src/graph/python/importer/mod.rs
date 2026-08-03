use crate::discovery::Document;
use ruff_python_ast::StmtImportFrom;

/// A Python module whose relative imports resolve from either the file or package itself.
#[derive(Clone, Copy)]
pub enum ImportingModule<'a> {
    File(&'a str),
    Package(&'a str),
}

impl<'a> ImportingModule<'a> {
    pub fn for_document(name: &'a str, document: &Document) -> Self {
        if document.relative.ends_with("/__init__.py") {
            Self::Package(name)
        } else {
            Self::File(name)
        }
    }

    pub fn resolve(self, item: &StmtImportFrom) -> String {
        let target = item
            .module
            .as_ref()
            .map(ToString::to_string)
            .unwrap_or_default();
        match item.level {
            0 => target,
            level => self.relative(level as usize, &target),
        }
    }

    fn join(package: String, target: &str) -> String {
        match (package.is_empty(), target.is_empty()) {
            (true, _) => target.to_string(),
            (false, true) => package,
            (false, false) => format!("{package}.{target}"),
        }
    }

    fn package_parts(self) -> Vec<&'a str> {
        let (name, includes_leaf) = match self {
            Self::File(name) => (name, true),
            Self::Package(name) => (name, false),
        };
        let mut parts = name.split('.').collect::<Vec<_>>();
        if includes_leaf {
            parts.pop();
        }
        parts
    }

    fn relative(self, level: usize, target: &str) -> String {
        let parts = self.package_parts();
        if level > parts.len() {
            return format!("{}{target}", ".".repeat(level));
        }
        let kept = parts.len() + 1 - level;
        Self::join(parts[..kept].join("."), target)
    }
}
