use crate::source::Source;
use serde_json::{Value, json};
use syn::spanned::Spanned;

use super::super::support::{locate, path_name};
use super::position::StatementPosition;

pub(super) fn block_children(source: &Source, block: &syn::Block) -> Vec<Value> {
    let last = block.stmts.len().checked_sub(1);
    block
        .stmts
        .iter()
        .enumerate()
        .map(|(at, statement)| {
            let position = match Some(at) == last {
                true => StatementPosition::Tail,
                false => StatementPosition::Body,
            };
            statement_tree(source, statement, position)
        })
        .collect()
}

fn statement_tree(source: &Source, statement: &syn::Stmt, position: StatementPosition) -> Value {
    let (kind, name) = statement_identity(statement, position);
    let span = match statement {
        syn::Stmt::Expr(held, Some(_)) => held.span(),
        _ => statement.span(),
    };
    json!({
        "kind": crate::syntax::known(kind),
        "name": name,
        "span": locate(source, span),
        "children": statement_children(source, statement),
    })
}

fn statement_identity(
    statement: &syn::Stmt,
    position: StatementPosition,
) -> (&'static str, String) {
    match statement {
        syn::Stmt::Local(held) => ("binding", local_name(&held.pat)),
        syn::Stmt::Item(_) => ("statement", String::new()),
        syn::Stmt::Macro(_) => ("effect", String::new()),
        syn::Stmt::Expr(held, semicolon) => match (semicolon, position) {
            (Some(_), _) => ("effect", expression_name(held)),
            (None, StatementPosition::Tail) => ("return", expression_name(held)),
            (None, StatementPosition::Body) => (expression_kind(held), expression_name(held)),
        },
    }
}

fn local_name(pattern: &syn::Pat) -> String {
    match pattern {
        syn::Pat::Ident(ident) => ident.ident.to_string(),
        syn::Pat::Type(typed) => match typed.pat.as_ref() {
            syn::Pat::Ident(ident) => ident.ident.to_string(),
            _ => String::new(),
        },
        _ => String::new(),
    }
}

fn statement_children(source: &Source, statement: &syn::Stmt) -> Vec<Value> {
    let effect = matches!(statement, syn::Stmt::Expr(_, Some(_)));
    match statement {
        syn::Stmt::Local(held) => held
            .init
            .iter()
            .map(|init| expression_tree(source, &init.expr))
            .collect(),
        syn::Stmt::Expr(held, _) if effect => vec![expression_tree(source, held)],
        syn::Stmt::Expr(held, _) => expression_children(source, held),
        _ => Vec::new(),
    }
}

pub(super) fn expression_kind(expression: &syn::Expr) -> &'static str {
    match expression {
        syn::Expr::Call(_) | syn::Expr::MethodCall(_) => "call",
        syn::Expr::Path(_) => "name",
        syn::Expr::Field(_) => "member",
        syn::Expr::Lit(syn::ExprLit {
            lit: syn::Lit::Str(_) | syn::Lit::ByteStr(_),
            ..
        }) => "text",
        syn::Expr::Lit(_) => "literal",
        syn::Expr::Array(_) | syn::Expr::Tuple(_) | syn::Expr::Struct(_) => "collection",
        syn::Expr::If(_) | syn::Expr::Match(_) => "branch",
        syn::Expr::ForLoop(_) | syn::Expr::While(_) | syn::Expr::Loop(_) => "loop",
        syn::Expr::Return(_) => "return",
        syn::Expr::Binary(_) | syn::Expr::Unary(_) => "operation",
        syn::Expr::Index(_) => "index",
        syn::Expr::Await(_) => "await",
        syn::Expr::Closure(_) => "callable",
        syn::Expr::Block(_) | syn::Expr::Unsafe(_) => "scope",
        _ => "expression",
    }
}

/// Return the name one expression states, which for a call is the whole path it reaches through.
///
/// A method call names its receiver as much as its method, and the reference frontend keeps both.
/// Dropping the receiver leaves `state.exec` reading as the bare `exec` that several languages
/// spell a scope builtin with, so every general rule matching a builtin by name answers yes for
/// any value holding a method of that name. A receiver no lexical reader can name leaves the call
/// unnamed rather than named after its method alone, which is the same answer Python gives.
pub(in crate::rust) fn expression_name(expression: &syn::Expr) -> String {
    match expression {
        syn::Expr::Path(path) => path_name(&path.path),
        syn::Expr::MethodCall(call) => {
            let reached = expression_name(&call.receiver);
            match reached.is_empty() {
                true => String::new(),
                false => format!("{reached}.{}", call.method),
            }
        }
        syn::Expr::Call(call) => expression_name(&call.func),
        syn::Expr::Field(field) => match &field.member {
            syn::Member::Named(name) => name.to_string(),
            syn::Member::Unnamed(index) => index.index.to_string(),
        },
        _ => String::new(),
    }
}

pub(super) fn expression_tree(source: &Source, expression: &syn::Expr) -> Value {
    json!({
        "kind": crate::syntax::known(expression_kind(expression)),
        "name": expression_name(expression),
        "span": locate(source, expression.span()),
        "children": expression_children(source, expression),
    })
}

/// Return the expressions one expression holds, which is what a tree walks into.
pub(super) fn expression_children(source: &Source, expression: &syn::Expr) -> Vec<Value> {
    let held: Vec<&syn::Expr> = match expression {
        syn::Expr::Call(call) => call.args.iter().collect(),
        syn::Expr::MethodCall(call) => std::iter::once(call.receiver.as_ref())
            .chain(call.args.iter())
            .collect(),
        syn::Expr::Binary(item) => vec![item.left.as_ref(), item.right.as_ref()],
        syn::Expr::Unary(item) => vec![item.expr.as_ref()],
        syn::Expr::Field(item) => vec![item.base.as_ref()],
        syn::Expr::Index(item) => vec![item.expr.as_ref(), item.index.as_ref()],
        syn::Expr::Await(item) => vec![item.base.as_ref()],
        syn::Expr::Return(item) => item.expr.as_deref().into_iter().collect(),
        syn::Expr::Reference(item) => vec![item.expr.as_ref()],
        syn::Expr::Paren(item) => vec![item.expr.as_ref()],
        syn::Expr::Array(item) => item.elems.iter().collect(),
        syn::Expr::Tuple(item) => item.elems.iter().collect(),
        syn::Expr::Block(item) => return block_children(source, &item.block),
        syn::Expr::Unsafe(item) => return block_children(source, &item.block),
        syn::Expr::Loop(item) => return block_children(source, &item.body),
        syn::Expr::While(item) => return block_children(source, &item.body),
        syn::Expr::ForLoop(item) => return block_children(source, &item.body),
        syn::Expr::If(item) => {
            let mut found = block_children(source, &item.then_branch);
            found.extend(
                item.else_branch
                    .iter()
                    .map(|(_, held)| expression_tree(source, held)),
            );
            return found;
        }
        syn::Expr::Match(item) => {
            return item
                .arms
                .iter()
                .map(|arm| expression_tree(source, &arm.body))
                .collect();
        }
        _ => Vec::new(),
    };
    held.into_iter()
        .map(|child| expression_tree(source, child))
        .collect()
}
