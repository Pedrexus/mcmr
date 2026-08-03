use crate::protocol::Node;
use crate::source::Source;
use crate::walk::{blocks, children};
use ruff_python_ast::{Expr, ModModule, Stmt};
use std::collections::BTreeMap;

/// Return the names one module lists in `__all__`, which are exported on purpose.
///
/// A module states its public surface once and then adds to it, so a name reached through `+=`,
/// through an annotated assignment, or from inside a branch is exported exactly as much as one in
/// the first list. Every string the stated value holds counts, which is what keeps a list built
/// out of other lists readable.
pub(crate) fn exported_names(module: &ModModule) -> Vec<String> {
    let mut exported = Vec::new();
    visit_module_statements(&module.body, &mut |statement| {
        if let Some(value) = stated_all_value(statement) {
            collect_strings(value, &mut exported);
        }
    });
    exported
}

/// Return each explicitly exported name beside every exact string node that states it.
pub(crate) fn exported_nodes(source: &Source, module: &ModModule) -> BTreeMap<String, Vec<Node>> {
    let mut exported = BTreeMap::new();
    visit_module_statements(&module.body, &mut |statement| {
        if let Some(value) = stated_all_value(statement) {
            collect_nodes(source, value, &mut exported);
        }
    });
    exported
}

/// Whether any statement declares or extends the module's explicit public surface.
pub(in crate::python) fn declares_all(module: &ModModule) -> bool {
    let mut found = false;
    visit_module_statements(&module.body, &mut |statement| {
        found |= stated_all_value(statement).is_some();
    });
    found
}

/// Visit statements that execute in module scope without entering a declaration body.
fn visit_module_statements(body: &[Stmt], visit: &mut impl FnMut(&Stmt)) {
    for statement in body {
        visit(statement);
        if matches!(statement, Stmt::ClassDef(_) | Stmt::FunctionDef(_)) {
            continue;
        }
        for block in blocks(statement) {
            visit_module_statements(block, visit);
        }
    }
}

/// Return the value that one module-scope statement assigns to `__all__`.
fn stated_all_value(statement: &Stmt) -> Option<&Expr> {
    match statement {
        Stmt::Assign(item) if item.targets.iter().any(is_dunder_all) => Some(&item.value),
        Stmt::AugAssign(item) if is_dunder_all(&item.target) => Some(&item.value),
        Stmt::AnnAssign(item) if is_dunder_all(&item.target) => item.value.as_deref(),
        _ => None,
    }
}

/// Collect every string one expression states, however deeply the expression nests them.
fn collect_strings(expression: &Expr, found: &mut Vec<String>) {
    if let Expr::StringLiteral(literal) = expression {
        found.push(literal.value.to_str().to_string());
    }
    for child in children(expression) {
        collect_strings(child, found);
    }
}

fn collect_nodes(source: &Source, expression: &Expr, found: &mut BTreeMap<String, Vec<Node>>) {
    if let Expr::StringLiteral(literal) = expression {
        found
            .entry(literal.value.to_str().to_string())
            .or_default()
            .push(source.node_of("sequence-item", literal));
    }
    for child in children(expression) {
        collect_nodes(source, child, found);
    }
}

fn is_dunder_all(target: &Expr) -> bool {
    matches!(target, Expr::Name(name) if name.id.as_str() == "__all__")
}
