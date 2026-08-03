use crate::source::Source;
use ruff_python_ast::ModModule;
use std::collections::BTreeMap;

/// Every class one file declares as evidence for repository class rules.
pub(super) struct Declared<'source> {
    pub(super) source: &'source Source,
    pub(super) module: &'source ModModule,
    pub(super) regions: Vec<usize>,
    pub(super) exported: Vec<String>,
    pub(super) bindings: BTreeMap<String, String>,
}
