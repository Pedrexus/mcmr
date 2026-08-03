use super::super::collections::stated;
use crate::source::Source;
use crate::walk::{blocks, body_range, children, statements, walk};
use ruff_python_ast::{Expr, ModModule, Stmt};
use ruff_text_size::Ranged;
use serde_json::{Value, json};
use std::collections::BTreeMap;

/// Return every `test` callable one module states, with whether a runner collects it.
pub(super) fn declared_tests(body: &[Stmt]) -> Vec<(&ruff_python_ast::StmtFunctionDef, bool)> {
    body.iter().flat_map(declared_in).collect()
}

fn declared_in(statement: &Stmt) -> Vec<(&ruff_python_ast::StmtFunctionDef, bool)> {
    match statement {
        Stmt::FunctionDef(item) if item.name.starts_with("test") => std::iter::once((item, true))
            .chain(nested_tests(&item.body))
            .collect(),
        Stmt::ClassDef(item) => class_tests(item),
        _ => blocks(statement)
            .into_iter()
            .flat_map(nested_tests)
            .collect(),
    }
}

fn class_tests(
    item: &ruff_python_ast::StmtClassDef,
) -> Vec<(&ruff_python_ast::StmtFunctionDef, bool)> {
    let collected = item.name.starts_with("Test") && !states_initializer(item);
    item.body
        .iter()
        .filter_map(|member| match member {
            Stmt::FunctionDef(method) if method.name.starts_with("test") => Some(method),
            _ => None,
        })
        .flat_map(|method| std::iter::once((method, collected)).chain(nested_tests(&method.body)))
        .collect()
}

/// Return every `test` callable declared under one body, none of which a runner reaches.
fn nested_tests(body: &[Stmt]) -> Vec<(&ruff_python_ast::StmtFunctionDef, bool)> {
    statements(body)
        .into_iter()
        .filter_map(|statement| match statement {
            Stmt::FunctionDef(item) if item.name.starts_with("test") => Some((item, false)),
            _ => None,
        })
        .collect()
}

/// Return statements one callable owns without entering declarations that start another scope.
pub(super) fn owned_statements(body: &[Stmt]) -> Vec<&Stmt> {
    let mut collected = Vec::new();
    let mut pending: Vec<&Stmt> = body.iter().rev().collect();
    while let Some(statement) = pending.pop() {
        collected.push(statement);
        if matches!(statement, Stmt::FunctionDef(_) | Stmt::ClassDef(_)) {
            continue;
        }
        for block in blocks(statement) {
            pending.extend(block.iter().rev());
        }
    }
    collected
}

pub(super) fn conditional_count(body: &[Stmt]) -> usize {
    owned_statements(body)
        .into_iter()
        .filter(|statement| matches!(statement, Stmt::If(_)))
        .count()
}

fn states_initializer(item: &ruff_python_ast::StmtClassDef) -> bool {
    item.body.iter().any(
        |member| matches!(member, Stmt::FunctionDef(method) if method.name.as_str() == "__init__"),
    )
}

/// Every sibling test whose syntax matches once its literals are removed.
///
/// The literals have to leave the syntax for two tests to be siblings at all, since the whole
/// question is whether they differ in nothing but their data. What each one stated travels beside
/// the shape as its own vector, so a rule can see whether the vectors repeat.
pub fn test_case_groups(source: &Source, module: &ModModule) -> Value {
    let mut shapes: BTreeMap<String, Vec<Vec<String>>> = BTreeMap::new();
    for statement in walk(module) {
        if let Stmt::FunctionDef(item) = statement
            && item.name.starts_with("test")
        {
            let (shape, vector) = literal_shape(source, &item.body);
            shapes.entry(shape).or_default().push(vector);
        }
    }
    let groups: Vec<Value> = shapes
        .into_iter()
        .map(|(syntax, vectors)| {
            json!({
                "normalized_syntax": syntax,
                "literal_vectors": vectors,
            })
        })
        .collect();
    json!({"groups": groups, "loops": literal_loops(module)})
}

/// Return one body written with every literal replaced, beside the literals it stated in order.
fn literal_shape(source: &Source, body: &[Stmt]) -> (String, Vec<String>) {
    let mut ranges = Vec::new();
    for statement in statements(body) {
        for expression in stated(statement) {
            collect_literal_ranges(expression, &mut ranges);
        }
    }
    ranges.sort_by_key(|range: &ruff_text_size::TextRange| range.start());
    let whole = body_range(body);
    let mut shape = String::new();
    let mut vector = Vec::new();
    let mut cursor = whole.start();
    for range in ranges {
        if range.start() < cursor {
            continue;
        }
        shape.push_str(source.slice(ruff_text_size::TextRange::new(cursor, range.start())));
        shape.push('?');
        vector.push(source.slice(range).to_string());
        cursor = range.end();
    }
    shape.push_str(source.slice(ruff_text_size::TextRange::new(cursor, whole.end())));
    (
        shape.split_whitespace().collect::<Vec<_>>().join(" "),
        vector,
    )
}

fn collect_literal_ranges(expression: &Expr, ranges: &mut Vec<ruff_text_size::TextRange>) {
    if matches!(
        expression,
        Expr::StringLiteral(_)
            | Expr::NumberLiteral(_)
            | Expr::BooleanLiteral(_)
            | Expr::NoneLiteral(_)
    ) {
        ranges.push(expression.range());
    }
    for child in children(expression) {
        collect_literal_ranges(child, ranges);
    }
}

/// Return every loop a test owns that walks a table of cases the source writes out.
fn literal_loops(module: &ModModule) -> Vec<Value> {
    let mut found = Vec::new();
    for (item, _) in declared_tests(&module.body) {
        for statement in statements(&item.body) {
            let Stmt::For(loop_statement) = statement else {
                continue;
            };
            let cases = match loop_statement.iter.as_ref() {
                Expr::List(held) => held.elts.len(),
                Expr::Tuple(held) => held.elts.len(),
                _ => continue,
            };
            found.push(json!({
                "case_count": cases,
                "owns_assertion": statements(&loop_statement.body)
                    .iter()
                    .any(|held| matches!(held, Stmt::Assert(_))),
            }));
        }
    }
    found
}
