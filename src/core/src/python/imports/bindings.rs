use crate::walk::walk;
use ruff_python_ast::{ModModule, Stmt};
use std::collections::BTreeMap;

/// Return what module each name one file imports came from.
pub(in crate::python) fn import_bindings(module: &ModModule) -> BTreeMap<String, String> {
    let mut bound = BTreeMap::new();
    for statement in walk(module) {
        bind_import(statement, &mut bound);
    }
    bound
}

fn bind_import(statement: &Stmt, bound: &mut BTreeMap<String, String>) {
    match statement {
        Stmt::Import(item) => item.names.iter().for_each(|alias| {
            let imported = alias.name.to_string();
            let name = alias
                .asname
                .as_ref()
                .map(ToString::to_string)
                .unwrap_or_else(|| imported.clone());
            bound.insert(name, imported);
        }),
        Stmt::ImportFrom(item) => bind_from_import(item, bound),
        _ => {}
    }
}

fn bind_from_import(item: &ruff_python_ast::StmtImportFrom, bound: &mut BTreeMap<String, String>) {
    let origin = item
        .module
        .as_ref()
        .map(ToString::to_string)
        .unwrap_or_default();
    for alias in &item.names {
        let name = alias
            .asname
            .as_ref()
            .map(ToString::to_string)
            .unwrap_or_else(|| alias.name.to_string());
        bound.insert(name, origin.clone());
    }
}
