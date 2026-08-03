use super::collections::owned;
use super::symbols::walk_expression;
use crate::source::Source;
use crate::walk::{blocks, children, qualified_name, walk};
use ruff_python_ast::{Expr, ModModule, Stmt};
use serde_json::{Value, json};
use std::collections::BTreeSet;

mod candidate;
mod context;

use candidate::set_loop_candidate;
pub(super) use context::complete_statement_expressions;
use context::{SetLoopContext, complete_stated_expressions, scope_binds_name};

/// Every comprehension one file writes and every loop that fills a set by hand.
pub(crate) fn comprehensions(source: &Source, module: &ModModule) -> Value {
    let mut counts = Vec::new();
    for statement in walk(module) {
        for expression in complete_statement_expressions(statement) {
            collect_comprehensions(expression, &mut counts);
        }
    }
    json!({"loop_counts": counts, "set_loop_candidates": set_loops(source, module)})
}

fn collect_comprehensions(expression: &Expr, counts: &mut Vec<usize>) {
    let generators = match expression {
        Expr::ListComp(item) => Some(item.generators.len()),
        Expr::SetComp(item) => Some(item.generators.len()),
        Expr::DictComp(item) => Some(item.generators.len()),
        Expr::Generator(item) => Some(item.generators.len()),
        _ => None,
    };
    if let Some(count) = generators {
        counts.push(count);
    }
    for child in children(expression) {
        collect_comprehensions(child, counts);
    }
}

fn set_loops(source: &Source, module: &ModModule) -> Vec<Value> {
    let mut candidates = Vec::new();
    collect_callable_set_loops(
        source,
        &module.body,
        usize::from(scope_binds_name(None, &module.body, "set")),
        &mut candidates,
    );
    candidates
}

/// Analyze each callable with the lexical bindings that control its builtin lookup.
fn collect_callable_set_loops(
    source: &Source,
    body: &[Stmt],
    set_shadow_depth: usize,
    candidates: &mut Vec<Value>,
) {
    for statement in body {
        match statement {
            Stmt::FunctionDef(function) => {
                collect_function_set_loops(source, function, set_shadow_depth, candidates)
            }
            Stmt::ClassDef(class) => {
                collect_callable_set_loops(source, &class.body, set_shadow_depth, candidates)
            }
            _ => {
                for nested in blocks(statement) {
                    collect_callable_set_loops(source, nested, set_shadow_depth, candidates);
                }
            }
        }
    }
}

fn collect_function_set_loops(
    source: &Source,
    function: &ruff_python_ast::StmtFunctionDef,
    set_shadow_depth: usize,
    candidates: &mut Vec<Value>,
) {
    let local_set_is_shadowed =
        scope_binds_name(Some(&function.parameters), &function.body, "set");
    let nested_shadow_depth = set_shadow_depth + usize::from(local_set_is_shadowed);
    if nested_shadow_depth == 0 && !scope_uses_dynamic_introspection(&function.body) {
        let external = external_names(&function.body);
        let context = SetLoopContext {
            function_body: &function.body,
            external: &external,
        };
        collect_set_loops(source, &function.body, &context, 0, candidates);
    }
    collect_callable_set_loops(source, &function.body, nested_shadow_depth, candidates);
}

/// Search one callable while retaining handler context and stopping at nested scopes.
fn collect_set_loops(
    source: &Source,
    body: &[Stmt],
    context: &SetLoopContext<'_>,
    handler_depth: usize,
    candidates: &mut Vec<Value>,
) {
    if handler_depth == 0 {
        candidates.extend(
            body.windows(2)
                .filter_map(|pair| set_loop_candidate(source, pair, context)),
        );
    }
    for statement in body {
        match statement {
            Stmt::FunctionDef(_) | Stmt::ClassDef(_) => {}
            Stmt::Try(item) => {
                collect_try_set_loops(source, item, context, handler_depth, candidates)
            }
            _ => {
                for nested in blocks(statement) {
                    collect_set_loops(source, nested, context, handler_depth, candidates);
                }
            }
        }
    }
}

fn collect_try_set_loops(
    source: &Source,
    item: &ruff_python_ast::StmtTry,
    context: &SetLoopContext<'_>,
    handler_depth: usize,
    candidates: &mut Vec<Value>,
) {
    collect_set_loops(source, &item.body, context, handler_depth, candidates);
    for handler in &item.handlers {
        let ruff_python_ast::ExceptHandler::ExceptHandler(clause) = handler;
        collect_set_loops(source, &clause.body, context, handler_depth + 1, candidates);
    }
    collect_set_loops(source, &item.orelse, context, handler_depth, candidates);
    collect_set_loops(source, &item.finalbody, context, handler_depth, candidates);
}

/// Return names declared `global` or `nonlocal` in one callable scope.
pub(super) fn external_names(body: &[Stmt]) -> BTreeSet<String> {
    owned(body)
        .into_iter()
        .flat_map(|statement| match statement {
            Stmt::Global(item) => item.names.iter().map(ToString::to_string).collect(),
            Stmt::Nonlocal(item) => item.names.iter().map(ToString::to_string).collect(),
            _ => Vec::new(),
        })
        .collect()
}

fn scope_uses_dynamic_introspection(body: &[Stmt]) -> bool {
    const DYNAMIC: &[&str] = &["locals", "globals", "vars", "eval", "exec"];
    owned(body).into_iter().any(|statement| {
        complete_stated_expressions(statement)
            .into_iter()
            .any(|expression| {
                walk_expression(expression).into_iter().any(|nested| {
                    matches!(nested, Expr::Call(call)
                    if DYNAMIC.contains(&qualified_name(&call.func).as_str()))
                })
            })
    })
}
