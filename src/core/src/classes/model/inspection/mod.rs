mod classes;
mod module;

use crate::discovery::{Document, Packages};
use crate::graph::ImportingModule;
use crate::source::Source;
use ruff_python_parser::parse_module;

use super::contracts::{ModuleShape, ModuleUsage, Stated};
use classes::declarations;
use module::{exported_names, imports, is_reexport_only, states_policy, usage};

impl Stated {
    pub(in crate::classes) fn of(document: &Document, packages: &Packages) -> Option<Self> {
        let parsed = parse_module(&document.source).ok()?;
        let module = parsed.syntax();
        let source = Source::new(document);
        let name = packages.module_name(&document.relative);
        let is_package = document.relative.ends_with("/__init__.py");
        let importer = ImportingModule::for_document(&name, document);
        let (called, read) = usage(module);
        Some(Self {
            declared: declarations(&source, module),
            imported: imports(module, importer),
            module: name,
            path: document.relative.clone(),
            shape: ModuleShape {
                is_package,
                is_reexport_only: is_reexport_only(module),
                states_policy: states_policy(module),
            },
            usage: ModuleUsage {
                called,
                read,
                exported: exported_names(module),
            },
        })
    }
}
