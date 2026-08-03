use crate::discovery::Document;
use ruff_python_ast::{Expr, Stmt};
use ruff_python_parser::parse_module;
use serde_json::{Value, json};

use super::super::assignment_scope::AssignmentScope;

/// Return literal collection assignments whose names can state discovery policy.
pub(super) fn configuration_assignments(documents: &[Document]) -> Vec<Value> {
    documents
        .iter()
        .filter(|document| document.relative.ends_with(".py"))
        .filter_map(|document| parse_module(&document.source).ok())
        .flat_map(|parsed| {
            let mut found = Vec::new();
            collect_assignments(&parsed.syntax().body, AssignmentScope::Ordinary, &mut found);
            found
        })
        .collect()
}

/// Walk assignments while retaining whether a configuration model owns each one.
fn collect_assignments(body: &[Stmt], scope: AssignmentScope, found: &mut Vec<Value>) {
    for statement in body {
        if let Some((Expr::Name(name), value)) = assignment(statement)
            && let Some((kind, values)) = string_collection(value)
        {
            found.push(json!({
                "name": name.id.to_string(),
                "collection_kind": kind,
                "values": values,
                "is_typed_configuration_field": matches!(scope, AssignmentScope::TypedConfiguration),
            }));
        }
        if let Some((nested, nested_scope)) = nested_assignments(statement) {
            collect_assignments(nested, nested_scope, found);
        }
    }
}

fn assignment(statement: &Stmt) -> Option<(&Expr, &Expr)> {
    match statement {
        Stmt::Assign(item) => item
            .targets
            .first()
            .filter(|_| item.targets.len() == 1)
            .map(|target| (target, item.value.as_ref())),
        Stmt::AnnAssign(item) => item
            .value
            .as_deref()
            .map(|value| (item.target.as_ref(), value)),
        _ => None,
    }
}

fn nested_assignments(statement: &Stmt) -> Option<(&[Stmt], AssignmentScope)> {
    match statement {
        Stmt::ClassDef(class) => Some((
            &class.body,
            if class.name.as_str().ends_with("Configuration") {
                AssignmentScope::TypedConfiguration
            } else {
                AssignmentScope::Ordinary
            },
        )),
        Stmt::FunctionDef(function) => Some((&function.body, AssignmentScope::Ordinary)),
        _ => None,
    }
}

/// Read one collection only when every element is a literal string.
fn string_collection(expression: &Expr) -> Option<(&'static str, Vec<String>)> {
    let (kind, elements) = match expression {
        Expr::List(item) => ("list", item.elts.as_slice()),
        Expr::Tuple(item) => ("tuple", item.elts.as_slice()),
        Expr::Set(item) => ("set", item.elts.as_slice()),
        _ => return None,
    };
    let values: Option<Vec<String>> = elements
        .iter()
        .map(|element| match element {
            Expr::StringLiteral(literal) => Some(literal.value.to_str().to_string()),
            _ => None,
        })
        .collect();
    Some((kind, values?))
}
