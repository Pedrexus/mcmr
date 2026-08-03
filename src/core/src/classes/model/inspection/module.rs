use std::collections::BTreeSet;

use crate::graph::{ImportingModule, absolute_module};
use crate::walk::{expression_tree, expressions, walk};
use ruff_python_ast::{Expr, ModModule, Stmt};

use super::super::contracts::Identity;
use super::classes::executable;

/// Return which names one module calls and which it names anywhere else, at any depth.
pub(super) fn usage(module: &ModModule) -> (BTreeSet<String>, BTreeSet<String>) {
    let mut called = BTreeSet::new();
    let mut read = BTreeSet::new();
    for expression in usage_expressions(module) {
        record_called_usage(expression, &mut called);
        record_read_usage(expression, &mut read);
    }
    (called, read)
}

fn usage_expressions(module: &ModModule) -> Vec<&Expr> {
    walk(module)
        .into_iter()
        .filter(|statement| !matches!(statement, Stmt::Import(_) | Stmt::ImportFrom(_)))
        .flat_map(stated_expressions)
        .flat_map(expression_tree)
        .collect()
}

fn stated_expressions(statement: &Stmt) -> Vec<&Expr> {
    match statement {
        Stmt::ClassDef(item) => item
            .decorator_list
            .iter()
            .map(|decorator| &decorator.expression)
            .collect(),
        _ => expressions(statement),
    }
}

fn record_called_usage(expression: &Expr, called: &mut BTreeSet<String>) {
    if let Expr::Call(item) = expression
        && let Expr::Name(name) = item.func.as_ref()
    {
        called.insert(name.id.to_string());
    }
}

fn record_read_usage(expression: &Expr, read: &mut BTreeSet<String>) {
    if let Expr::Name(name) = expression {
        read.insert(name.id.to_string());
    }
}

/// Return every explicit `from` import one module states, as the module and name it reaches.
pub(super) fn imports(module: &ModModule, importer: ImportingModule<'_>) -> Vec<Identity> {
    module
        .body
        .iter()
        .filter_map(|statement| match statement {
            Stmt::ImportFrom(item) => Some(item),
            _ => None,
        })
        .flat_map(|item| {
            let target = absolute_module(importer, item);
            item.names
                .iter()
                .filter(|alias| alias.name.as_str() != "*")
                .map(move |alias| (target.clone(), alias.name.to_string()))
        })
        .collect()
}

/// Whether this project has established which model foundation its own classes derive.
pub(super) fn states_policy(module: &ModModule) -> bool {
    module.body.iter().any(|statement| match statement {
        Stmt::ImportFrom(item) => {
            item.module
                .as_ref()
                .map(ToString::to_string)
                .is_some_and(|origin| {
                    origin.split('.').next().unwrap_or(&origin) == "patos"
                        || origin.ends_with("bases")
                })
        }
        _ => false,
    })
}

/// Whether one module hands names on rather than declaring anything of its own.
pub(super) fn is_reexport_only(module: &ModModule) -> bool {
    executable(&module.body)
        .iter()
        .all(|statement| match statement {
            Stmt::Import(_) | Stmt::ImportFrom(_) => true,
            Stmt::Assign(item) => item
                .targets
                .iter()
                .all(|target| matches!(target, Expr::Name(name) if name.id.as_str() == "__all__")),
            _ => false,
        })
}

/// Return the names one module lists in `__all__`, which are exported on purpose.
pub(super) fn exported_names(module: &ModModule) -> Vec<String> {
    module
        .body
        .iter()
        .filter_map(|statement| match statement {
            Stmt::Assign(item)
                if item
                    .targets
                    .iter()
                    .any(|target| matches!(target, Expr::Name(name) if name.id == "__all__")) =>
            {
                Some(&item.value)
            }
            _ => None,
        })
        .flat_map(|value| expression_tree(value))
        .filter_map(|element| match element {
            Expr::StringLiteral(literal) => Some(literal.value.to_str().to_string()),
            _ => None,
        })
        .collect()
}
