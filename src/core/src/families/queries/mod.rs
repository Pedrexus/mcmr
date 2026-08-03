use crate::source::Source;
use crate::walk::{blocks, children, expressions, qualified_name};
use ruff_python_ast::{Expr, ExprCall, ModModule, Stmt};
use ruff_text_size::Ranged;
use serde_json::{Value, json};

mod context;
mod scope;

use context::SqlModelContext;
use scope::QueryScope;

/// Every database operation chain one file writes through SQLAlchemy or SQLModel.
pub fn queries(source: &Source, module: &ModModule) -> Value {
    let sqlmodel = SqlModelContext::of(module);
    let mut operations = Vec::new();
    collect_query_statements(
        source,
        &module.body,
        QueryScope::OutsideLoop,
        &sqlmodel,
        &mut operations,
    );
    json!({"operations": operations})
}

/// Walk statements once while retaining whether execution sits inside a loop.
fn collect_query_statements(
    source: &Source,
    body: &[Stmt],
    scope: QueryScope,
    sqlmodel: &SqlModelContext,
    found: &mut Vec<Value>,
) {
    for statement in body {
        for expression in expressions(statement) {
            collect_queries(source, expression, scope, sqlmodel, found);
        }
        for nested in blocks(statement) {
            collect_query_statements(source, nested, scope.nested(statement), sqlmodel, found);
        }
    }
}

fn collect_queries(
    source: &Source,
    expression: &Expr,
    scope: QueryScope,
    sqlmodel: &SqlModelContext,
    found: &mut Vec<Value>,
) {
    if let Some(operation) = scalar_operation(source, expression, scope, sqlmodel) {
        found.push(operation);
    }
    if let Some(operation) = primary_key_operation(source, expression, scope, sqlmodel) {
        found.push(operation);
    }
    if let Expr::Call(item) = expression {
        let name = qualified_name(&item.func);
        if let Some(kind) = query_kind(&name) {
            // A session factory states its settling policy through its keywords. Preserve unknown
            // keywords because they can change what the factory does.
            const KNOWN: &[&str] = &[
                "bind",
                "class_",
                "expire_on_commit",
                "autoflush",
                "autobegin",
                "info",
                "join_transaction_mode",
            ];
            let keywords = &item.arguments.keywords;
            found.push(json!({
                "kind": kind,
                "framework": "sqlalchemy",
                "is_inside_loop": scope.is_inside_loop(),
                "expire_on_commit": keywords
                    .iter()
                    .find(|keyword| {
                        keyword.arg.as_ref().is_some_and(|named| named == "expire_on_commit")
                    })
                    .is_none_or(|keyword| !matches!(&keyword.value, Expr::BooleanLiteral(held)
                        if !held.value)),
                "has_unknown_keywords": keywords.iter().any(|keyword| {
                    keyword
                        .arg
                        .as_ref()
                        .is_none_or(|named| !KNOWN.contains(&named.as_str()))
                }),
                "node": source.node_of("call", item),
            }));
        }
    }
    for child in children(expression) {
        collect_queries(source, child, scope, sqlmodel, found);
    }
}

/// Recognize one resolved SQLModel scalar extraction chain and retain its editable segments.
fn scalar_operation(
    source: &Source,
    expression: &Expr,
    scope: QueryScope,
    sqlmodel: &SqlModelContext,
) -> Option<Value> {
    let Expr::Call(scalars) = expression else {
        return None;
    };
    let executed = method_receiver(scalars, "scalars")?;
    if !scalars.arguments.args.is_empty() || !scalars.arguments.keywords.is_empty() {
        return None;
    }
    let Expr::Call(execute) = executed else {
        return None;
    };
    let method = called_method(execute)?;
    if !matches!(method.attr.as_str(), "exec" | "execute")
        || !sqlmodel.is_session_receiver(&method.value)
        || !execute.arguments.keywords.is_empty()
    {
        return None;
    }
    let [query] = execute.arguments.args.as_ref() else {
        return None;
    };
    let (selected_expression_count, has_execution_options) = selection(query, sqlmodel)?;
    let scalars_range = ruff_text_size::TextRange::new(execute.end(), scalars.end());
    Some(json!({
        "kind": if method.attr.as_str() == "exec" { "exec_scalars" } else { "execute_scalars" },
        "framework": "sqlmodel",
        "is_inside_loop": scope.is_inside_loop(),
        "selected_expression_count": selected_expression_count,
        "has_execution_options": has_execution_options,
        "node": source.node_of("call", scalars),
        "execute_segment": source.node("method", method.attr.range),
        "scalars_segment": source.node("call-segment", scalars_range),
    }))
}

/// Recognize one exact local-table primary-key lookup through SQLModel `Session.exec`.
fn primary_key_operation(
    source: &Source,
    expression: &Expr,
    scope: QueryScope,
    sqlmodel: &SqlModelContext,
) -> Option<Value> {
    let Expr::Call(first) = expression else {
        return None;
    };
    let (execute, query) = executed_query(first)?;
    let method = called_method(execute)?;
    if !sqlmodel.is_session_receiver(&method.value) {
        return None;
    }
    let (query, has_execution_options) = without_execution_options(query);
    if !is_primary_key_selection(query, sqlmodel) {
        return None;
    }
    Some(json!({
        "kind": "primary_key_first",
        "framework": "sqlmodel",
        "is_inside_loop": scope.is_inside_loop(),
        "selected_expression_count": 1,
        "has_primary_key_equality": true,
        "has_execution_options": has_execution_options,
        "node": source.node_of("call", first),
    }))
}

fn executed_query(first: &ExprCall) -> Option<(&ExprCall, &Expr)> {
    let executed = method_receiver(first, "first")?;
    if !first.arguments.args.is_empty() || !first.arguments.keywords.is_empty() {
        return None;
    }
    let Expr::Call(execute) = executed else {
        return None;
    };
    let method = called_method(execute)?;
    if method.attr.as_str() != "exec" || !execute.arguments.keywords.is_empty() {
        return None;
    }
    let [query] = execute.arguments.args.as_ref() else {
        return None;
    };
    Some((execute, query))
}

fn is_primary_key_selection(query: &Expr, sqlmodel: &SqlModelContext) -> bool {
    let Expr::Call(where_call) = query else {
        return false;
    };
    let Some(selected) = method_receiver(where_call, "where") else {
        return false;
    };
    if !where_call.arguments.keywords.is_empty() {
        return false;
    }
    let [predicate] = where_call.arguments.args.as_ref() else {
        return false;
    };
    let Expr::Call(select) = selected else {
        return false;
    };
    if !sqlmodel.is_select(select) || !select.arguments.keywords.is_empty() {
        return false;
    }
    let [model] = select.arguments.args.as_ref() else {
        return false;
    };
    let model_name = qualified_name(model);
    let model_name = model_name.rsplit('.').next().unwrap_or(&model_name);
    sqlmodel.is_primary_key_equality(predicate, model_name)
}

fn called_method(call: &ExprCall) -> Option<&ruff_python_ast::ExprAttribute> {
    match call.func.as_ref() {
        Expr::Attribute(method) => Some(method),
        _ => None,
    }
}

fn method_receiver<'call>(call: &'call ExprCall, name: &str) -> Option<&'call Expr> {
    let method = called_method(call)?;
    (method.attr.as_str() == name).then_some(method.value.as_ref())
}

fn selection(expression: &Expr, sqlmodel: &SqlModelContext) -> Option<(usize, bool)> {
    let mut current = expression;
    let mut has_execution_options = false;
    loop {
        let Expr::Call(call) = current else {
            return None;
        };
        if sqlmodel.is_select(call) {
            return Some((call.arguments.args.len(), has_execution_options));
        }
        let method = called_method(call)?;
        has_execution_options |= method.attr.as_str() == "execution_options";
        current = &method.value;
    }
}

fn without_execution_options(expression: &Expr) -> (&Expr, bool) {
    let Expr::Call(call) = expression else {
        return (expression, false);
    };
    let Some(method) = called_method(call) else {
        return (expression, false);
    };
    match method.attr.as_str() {
        "execution_options" => (&method.value, true),
        _ => (expression, false),
    }
}

fn query_kind(name: &str) -> Option<&'static str> {
    let tail = name.rsplit('.').next().unwrap_or(name);
    match tail {
        "async_sessionmaker" => Some("async_sessionmaker"),
        "commit" => Some("session_commit"),
        _ => None,
    }
}
