use crate::protocol::Span;
use crate::source::Source;
use crate::walk::{qualified_name, statements};
use ruff_python_ast::token::{TokenKind, Tokens};
use ruff_python_ast::{Expr, Stmt, StmtFunctionDef};
use ruff_text_size::Ranged;
use serde_json::{Value, json};
use std::collections::BTreeMap;

use super::super::comments::comment_body;
use super::super::functions::support::executable;

mod pass_through;

use pass_through::passes_through;

/// Return the key and value of every pair a sequence of two element tuples states.
pub(super) fn pairs(elements: &[Expr]) -> (Vec<String>, Vec<&Expr>) {
    let held: Vec<(String, &Expr)> = elements
        .iter()
        .filter_map(|element| match element {
            Expr::Tuple(pair) => match pair.elts.as_slice() {
                [key, value] => literal_text(key).map(|named| (named, value)),
                _ => None,
            },
            _ => None,
        })
        .collect();
    (
        held.iter().map(|(named, _)| named.clone()).collect(),
        held.into_iter().map(|(_, value)| value).collect(),
    )
}

/// Group the attribute reads of one structure by the object each one starts from.
pub(super) fn projection_groups(keys: &[String], reads: &[&Expr], span: &Span) -> Vec<Value> {
    let mut roots: BTreeMap<&str, Vec<String>> = BTreeMap::new();
    for read in reads {
        if let Expr::Attribute(item) = read
            && let Expr::Name(held) = item.value.as_ref()
        {
            roots
                .entry(held.id.as_str())
                .or_default()
                .push(item.attr.to_string());
        }
    }
    roots
        .into_iter()
        .map(|(root, attributes)| {
            json!({
                "root": root,
                "span": span,
                "attribute_names": attributes,
                "output_keys": keys,
            })
        })
        .collect()
}

/// Return what one literal says, when the expression is a literal a key can be written as.
pub(super) fn literal_text(expression: &Expr) -> Option<String> {
    match expression {
        Expr::StringLiteral(literal) => Some(literal.value.to_str().to_string()),
        _ => None,
    }
}

/// Return the line each `# region` marker opens a new independently ordered section on.
pub(super) fn region_lines(source: &Source, tokens: &Tokens) -> Vec<usize> {
    tokens
        .iter()
        .filter(|token| token.kind() == TokenKind::Comment)
        .filter(|token| {
            comment_body(source.slice(token.range()))
                .trim_start_matches('#')
                .trim_start()
                .to_ascii_lowercase()
                .starts_with("region")
        })
        .map(|token| source.line_of(token.range().start()))
        .collect()
}

/// Whether one class body assigns the registry key its own name already derives.
pub(super) fn states_registry_name(body: &[Stmt]) -> bool {
    body.iter().any(|member| match member {
        Stmt::Assign(item) => {
            item.targets
                .iter()
                .any(|target| matches!(target, Expr::Name(held) if held.id.as_str() == "name"))
                && matches!(item.value.as_ref(), Expr::StringLiteral(_))
        }
        Stmt::AnnAssign(item) => {
            matches!(item.target.as_ref(), Expr::Name(held) if held.id.as_str() == "name")
                && matches!(item.value.as_deref(), Some(Expr::StringLiteral(_)))
        }
        _ => false,
    })
}

/// Whether one statement stands in for a body rather than being one.
pub(super) fn is_placeholder(statement: &Stmt) -> bool {
    match statement {
        Stmt::Pass(_) => true,
        Stmt::Expr(item) => matches!(item.value.as_ref(), Expr::EllipsisLiteral(_)),
        _ => false,
    }
}

/// Whether one statement binds one name, which is what lets a body shadow the class holding it.
pub(super) fn binds(statement: &Stmt, name: &str) -> bool {
    let targets: Vec<&Expr> = match statement {
        Stmt::Assign(item) => item.targets.iter().collect(),
        Stmt::AnnAssign(item) => vec![item.target.as_ref()],
        Stmt::For(item) => vec![item.target.as_ref()],
        _ => return false,
    };
    targets
        .into_iter()
        .any(|target| matches!(target, Expr::Name(held) if held.id.as_str() == name))
}

/// Return every field one body stores on its receiver, with the expression it stored.
pub(super) fn assignments(body: &[Stmt]) -> Vec<(String, &Expr)> {
    statements(body)
        .into_iter()
        .filter_map(|statement| match statement {
            Stmt::Assign(item) => match item.targets.as_slice() {
                [Expr::Attribute(field)] => Some((field, item.value.as_ref())),
                _ => None,
            },
            Stmt::AnnAssign(item) => match (item.target.as_ref(), item.value.as_deref()) {
                (Expr::Attribute(field), Some(value)) => Some((field, value)),
                _ => None,
            },
            _ => None,
        })
        .filter(|(field, _)| matches!(field.value.as_ref(), Expr::Name(held) if held.id == "self"))
        .map(|(field, value)| (field.attr.to_string(), value))
        .collect()
}

/// Whether one method hands every argument it was given straight to the same method above it.
pub(super) fn forwards_to_super(item: &StmtFunctionDef) -> bool {
    let [Stmt::Return(returned)] = executable(&item.body) else {
        return false;
    };
    let Some(Expr::Call(call)) = returned.value.as_deref() else {
        return false;
    };
    let Expr::Attribute(member) = call.func.as_ref() else {
        return false;
    };
    let Expr::Call(receiver) = member.value.as_ref() else {
        return false;
    };
    member.attr.as_str() == item.name.as_str()
        && qualified_name(&receiver.func) == "super"
        && receiver.arguments.args.is_empty()
        && passes_through(&item.parameters, &call.arguments)
}
