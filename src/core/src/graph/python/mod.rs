use super::contracts::Stated;
use crate::source::Source;

mod collector;
mod importer;

use collector::Collector;
pub use importer::ImportingModule;

/// Return the absolute module named by one import in its typed importing context.
pub fn absolute_module(
    importer: ImportingModule<'_>,
    item: &ruff_python_ast::StmtImportFrom,
) -> String {
    importer.resolve(item)
}

pub(crate) fn python(source: Source, module: &str) -> Option<Stated> {
    Collector::collect(source, module)
}
