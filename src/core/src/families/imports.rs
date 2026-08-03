use ruff_python_ast::{ModModule, Stmt};
use std::collections::BTreeMap;

/// Return direct import aliases as the qualified name each local binding denotes.
pub(super) fn direct_imports(module: &ModModule) -> BTreeMap<String, String> {
    let mut imports = BTreeMap::new();
    for statement in &module.body {
        match statement {
            Stmt::Import(imported) => insert_direct_imports(imported, &mut imports),
            Stmt::ImportFrom(imported) => insert_from_imports(imported, &mut imports),
            _ => {}
        }
    }
    imports
}

fn insert_direct_imports(
    imported: &ruff_python_ast::StmtImport,
    imports: &mut BTreeMap<String, String>,
) {
    for alias in &imported.names {
        let local = alias
            .asname
            .as_ref()
            .map(ToString::to_string)
            .unwrap_or_else(|| {
                alias
                    .name
                    .as_str()
                    .split('.')
                    .next()
                    .expect("an import name must hold a component")
                    .to_string()
            });
        imports.insert(local, alias.name.to_string());
    }
}

fn insert_from_imports(
    imported: &ruff_python_ast::StmtImportFrom,
    imports: &mut BTreeMap<String, String>,
) {
    let Some(module) = imported.module.as_ref() else {
        return;
    };
    for alias in &imported.names {
        let local = alias.asname.as_ref().unwrap_or(&alias.name).to_string();
        imports.insert(local, format!("{module}.{}", alias.name));
    }
}

/// Resolve the imported head of one dotted name while retaining its local tail.
pub(super) fn resolve_imported(imports: &BTreeMap<String, String>, written: &str) -> String {
    let (head, tail) = written.split_once('.').unwrap_or((written, ""));
    let Some(origin) = imports.get(head) else {
        return written.to_string();
    };
    if tail.is_empty() {
        origin.clone()
    } else {
        format!("{origin}.{tail}")
    }
}
