use crate::functions::FunctionRecord;
use crate::source::Source;
use ruff_python_ast::ModModule;

use super::asyncio::Asyncio;

pub(super) struct FunctionCollector<'a> {
    pub(super) source: &'a Source,
    pub(super) asyncio: Asyncio,
    pub(super) facts: Vec<FunctionRecord>,
}

impl<'a> FunctionCollector<'a> {
    pub(super) fn new(source: &'a Source, module: &ModModule) -> Self {
        Self {
            source,
            asyncio: Asyncio::of(module),
            facts: Vec::new(),
        }
    }
}
