use crate::calls::CallSite as TypedCallSite;
use crate::source::Source;
use crate::walk::walk;
use ruff_python_ast::{ModModule, Stmt};
use std::collections::{BTreeMap, BTreeSet};

pub(super) struct CallCollector<'a> {
    pub(super) source: &'a Source,
    pub(super) ambiguous: BTreeSet<String>,
    pub(super) calls: Vec<TypedCallSite>,
}

/// Return imported names that more than one binding claims in this module.
pub(super) fn ambiguous_imports(module: &ModModule) -> BTreeSet<String> {
    let mut counts: BTreeMap<String, usize> = BTreeMap::new();
    for statement in walk(module) {
        count_import_bindings(statement, &mut counts);
    }
    counts
        .into_iter()
        .filter_map(|(name, count)| (count > 1).then_some(name))
        .collect()
}

fn count_import_bindings(statement: &Stmt, counts: &mut BTreeMap<String, usize>) {
    match statement {
        Stmt::Import(item) => item.names.iter().for_each(|alias| {
            let imported = alias.name.to_string();
            let bound = alias
                .asname
                .as_ref()
                .map(ToString::to_string)
                .unwrap_or_else(|| imported.split('.').next().unwrap_or(&imported).to_string());
            *counts.entry(bound).or_default() += 1;
        }),
        Stmt::ImportFrom(item) => item.names.iter().for_each(|alias| {
            let bound = alias
                .asname
                .as_ref()
                .map(ToString::to_string)
                .unwrap_or_else(|| alias.name.to_string());
            *counts.entry(bound).or_default() += 1;
        }),
        _ => {}
    }
}

impl<'a> CallCollector<'a> {
    pub(super) fn new(source: &'a Source, ambiguous: BTreeSet<String>) -> Self {
        Self {
            source,
            ambiguous,
            calls: Vec::new(),
        }
    }
}
