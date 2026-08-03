use super::fact::{base, is_test_module};
use super::imports::declares_all;
use crate::protocol::JsonObject;
use crate::source::Source;
use crate::walk::{children, declared_name, docstring, qualified_name, walk};
use ruff_python_ast::{Expr, ExprContext, ModModule, Stmt};
use ruff_text_size::Ranged;
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};

pub(super) fn module_fact(source: &Source, module: &ModModule) -> Value {
    let classes = module
        .body
        .iter()
        .filter(|item| matches!(item, Stmt::ClassDef(_)))
        .count();
    let functions = module
        .body
        .iter()
        .filter(|item| matches!(item, Stmt::FunctionDef(_)))
        .count();
    let imports_only = module.body.iter().all(|item| {
        matches!(item, Stmt::Import(_) | Stmt::ImportFrom(_)) || declares_all_statement(item)
    });
    let members: Vec<Value> = module
        .body
        .iter()
        .filter_map(|item| {
            declared_name(item).map(|name| {
                json!({
                    "name": name,
                    "kind": match item {
                        Stmt::ClassDef(_) => "class",
                        Stmt::FunctionDef(_) => "function",
                        _ => "unknown",
                    },
                    "source": source.slice(item.range()),
                })
            })
        })
        .collect();
    let all_declarations = module
        .body
        .iter()
        .filter(|statement| declares_all_statement(statement))
        .map(|statement| source.node_of("statement", statement))
        .collect::<Vec<_>>();
    let key = format!("module:{}", source.relative);
    JsonObject::new(base(source, &key, module.range())).merged(json!({
        "physical_line_count": source.text.lines().count(),
        "statement_count": walk(module).len(),
        "class_count": classes,
        "function_count": functions,
        "executable_statement_count": module.body.len()
            - usize::from(docstring(&module.body).is_some()),
        "is_package_initializer": source.relative.ends_with("__init__.py"),
        "is_test": is_test_module(source),
        "declares_all": declares_all(module),
        "all_declarations": all_declarations,
        "has_only_imports_and_all": imports_only,
        "constant_placements": constant_placements(module),
        "members": members,
    }))
}

/// Whether one top-level statement declares or extends `__all__`.
fn declares_all_statement(statement: &Stmt) -> bool {
    match statement {
        Stmt::Assign(item) => item.targets.iter().any(is_dunder_all),
        Stmt::AugAssign(item) => is_dunder_all(&item.target),
        Stmt::AnnAssign(item) => is_dunder_all(&item.target),
        _ => false,
    }
}

/// Whether one assignment target is the module public-surface declaration.
fn is_dunder_all(target: &Expr) -> bool {
    matches!(target, Expr::Name(name) if name.id.as_str() == "__all__")
}

/// Locate each public module constant against the latest statement its initializer needs.
fn constant_placements(module: &ModModule) -> Vec<Value> {
    let mut declarations: BTreeMap<String, usize> = BTreeMap::new();
    let mut latest_import = None;
    let mut placements = Vec::new();
    for (index, statement) in module.body.iter().enumerate() {
        if matches!(statement, Stmt::Import(_) | Stmt::ImportFrom(_)) {
            latest_import = Some(index);
        }
        let Some((name, value)) = constant_assignment(statement) else {
            if let Some(name) = module_declaration_name(statement) {
                declarations.insert(name, index);
            }
            continue;
        };
        let mut dependencies = BTreeSet::new();
        expression_names(value, &mut dependencies);
        let anchor = dependencies
            .iter()
            .filter_map(|name| declarations.get(*name))
            .copied()
            .chain(latest_import)
            .max();
        let start = anchor.map_or(0, |position| position + 1);
        let intervening = module.body[start..index]
            .iter()
            .filter(|candidate| !is_placement_scaffolding(candidate))
            .count();
        placements.push(json!({
            "name": name,
            "intervening_statement_count": intervening,
        }));
        declarations.insert(name.to_string(), index);
    }
    placements
}

/// Return the one module name a statement makes available to later initializers.
fn module_declaration_name(statement: &Stmt) -> Option<String> {
    match statement {
        Stmt::Assign(item) if item.targets.len() == 1 => Some(qualified_name(&item.targets[0])),
        Stmt::AnnAssign(item) => Some(qualified_name(&item.target)),
        _ => declared_name(statement),
    }
    .filter(|name| !name.is_empty())
}

/// Return one public uppercase assignment and the expression that initializes it.
fn constant_assignment(statement: &Stmt) -> Option<(&str, &Expr)> {
    let (target, value) = match statement {
        Stmt::Assign(item) if item.targets.len() == 1 => (&item.targets[0], item.value.as_ref()),
        Stmt::AnnAssign(item) => (item.target.as_ref(), item.value.as_deref()?),
        _ => return None,
    };
    let Expr::Name(name) = target else {
        return None;
    };
    let name = name.id.as_str();
    (!name.starts_with('_')
        && name.chars().any(char::is_alphabetic)
        && name.chars().all(|character| !character.is_lowercase()))
    .then_some((name, value))
}

/// Collect every loaded name one initializer states directly or below another expression.
fn expression_names<'expression>(
    expression: &'expression Expr,
    names: &mut BTreeSet<&'expression str>,
) {
    if let Expr::Name(name) = expression
        && name.ctx == ExprContext::Load
    {
        names.insert(name.id.as_str());
    }
    for child in children(expression) {
        expression_names(child, names);
    }
}

/// Whether one statement may stay between an anchor and another constant without separating them.
fn is_placement_scaffolding(statement: &Stmt) -> bool {
    let typing_guard = match statement {
        Stmt::If(item) => {
            matches!(item.test.as_ref(), Expr::Name(name) if name.id == "TYPE_CHECKING")
        }
        _ => false,
    };
    let pytest_configuration = match statement {
        Stmt::Assign(item) => item.targets.iter().any(|target| {
            matches!(target, Expr::Name(name)
                if matches!(name.id.as_str(), "pytestmark" | "pytest_plugins"))
        }),
        _ => false,
    };
    matches!(statement, Stmt::Import(_) | Stmt::ImportFrom(_))
        || docstring(std::slice::from_ref(statement)).is_some()
        || constant_assignment(statement).is_some()
        || typing_guard
        || pytest_configuration
        || matches!(statement, Stmt::Assign(item)
        if item.targets.iter().any(|target| {
            matches!(target, Expr::Name(name) if name.id.starts_with("__"))
        }))
}
