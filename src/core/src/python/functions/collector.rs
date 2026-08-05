use crate::functions::FunctionRecord;
use crate::source::Source;
use ruff_python_ast::ModModule;

use super::support::ModuleContext;

pub(super) struct FunctionCollector<'a> {
    pub(super) source: &'a Source,
    pub(super) context: ModuleContext,
    pub(super) facts: Vec<FunctionRecord>,
}

impl<'a> FunctionCollector<'a> {
    pub(super) fn new(source: &'a Source, module: &ModModule) -> Self {
        Self {
            source,
            context: ModuleContext::of(module),
            facts: Vec::new(),
        }
    }
}
