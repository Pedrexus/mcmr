use super::collections::owned;
use super::comprehensions::external_names;
use crate::source::Source;
use crate::walk::walk;
use ruff_python_ast::{Expr, ModModule, Stmt};
use ruff_text_size::Ranged;
use serde_json::{Value, json};
use std::collections::BTreeMap;

mod analysis;

use analysis::{statement_contains_raising_operation, try_clause_statement_counts};

/// Every try statement one file protects, with the sizes of its clauses.
pub fn try_blocks(source: &Source, module: &ModModule) -> Value {
    let mut setups = function_try_setups(source, module);
    let regions: Vec<Value> = walk(module)
        .into_iter()
        .filter_map(|statement| match statement {
            Stmt::Try(item) => {
                let setup = setups
                    .remove(&u32::from(item.range.start()))
                    .unwrap_or_default();
                Some(json!({
                    "leading_literal_assignment_count": setup.leading_assignments.len(),
                    "has_following_raising_operation": setup.has_following_raising_operation,
                    "clause_statement_counts": try_clause_statement_counts(item),
                    "statement": source.node_of("try", statement),
                    "leading_assignments": setup.leading_assignments,
                    "protected_statements": item.body.iter().map(|held| source.node_of("statement", held)).collect::<Vec<_>>(),
                    "handlers": item.handlers.iter().map(|handler| exception_handler(source, handler)).collect::<Vec<_>>(),
                    "has_else": !item.orelse.is_empty(),
                    "has_finally": !item.finalbody.is_empty(),
                    "is_exception_group": item.is_star,
                }))
            }
            _ => None,
        })
        .collect();
    json!({"regions": regions})
}

fn exception_handler(source: &Source, handler: &ruff_python_ast::ExceptHandler) -> Value {
    let ruff_python_ast::ExceptHandler::ExceptHandler(held) = handler;
    json!({
        "caught": held.type_.as_deref().map_or("", |caught| source.slice(caught.range())),
        "caught_is_tuple": matches!(held.type_.as_deref(), Some(Expr::Tuple(_))),
        "alias": held.name.as_ref().map_or("", |name| name.as_str()),
        "body": held.body.iter().map(|statement| source.node_of("statement", statement)).collect::<Vec<_>>(),
    })
}

#[derive(Default)]
struct TrySetup {
    leading_assignments: Vec<Value>,
    has_following_raising_operation: bool,
}

/// Return movable setup only for ordinary tries owned by a callable scope.
fn function_try_setups(source: &Source, module: &ModModule) -> BTreeMap<u32, TrySetup> {
    let mut found = BTreeMap::new();
    for statement in walk(module) {
        if let Stmt::FunctionDef(function) = statement {
            collect_function_setups(source, &function.body, &mut found);
        }
    }
    found
}

fn collect_function_setups(source: &Source, body: &[Stmt], found: &mut BTreeMap<u32, TrySetup>) {
    let external = external_names(body);
    for statement in owned(body) {
        if let Stmt::Try(item) = statement
            && let Some(setup) = try_setup(source, item, &external)
        {
            found.insert(u32::from(item.range.start()), setup);
        }
    }
}

fn try_setup(
    source: &Source,
    item: &ruff_python_ast::StmtTry,
    external: &std::collections::BTreeSet<String>,
) -> Option<TrySetup> {
    if item.is_star || !item.finalbody.is_empty() {
        return None;
    }
    let leading_assignments = movable_assignments(source, &item.body, external);
    let leading_count = leading_assignments.len();
    Some(TrySetup {
        leading_assignments,
        has_following_raising_operation: leading_count > 0
            && item
                .body
                .get(leading_count)
                .is_some_and(statement_contains_raising_operation),
    })
}

fn movable_assignments(
    source: &Source,
    body: &[Stmt],
    external: &std::collections::BTreeSet<String>,
) -> Vec<Value> {
    body.iter()
        .enumerate()
        .map_while(|(index, statement)| {
            let name = literal_local_assignment(statement)?;
            (!external.contains(name) && !assignment_has_type_comment(source, body, index)).then(
                || {
                    serde_json::to_value(source.node_of("statement", statement))
                        .expect("a source node must serialize")
                },
            )
        })
        .collect()
}

/// Return the sole local name one exact `ast.Constant` assignment initializes.
fn literal_local_assignment(statement: &Stmt) -> Option<&str> {
    let Stmt::Assign(item) = statement else {
        return None;
    };
    let [Expr::Name(target)] = item.targets.as_slice() else {
        return None;
    };
    is_constant_literal(&item.value).then_some(target.id.as_str())
}

fn is_constant_literal(expression: &Expr) -> bool {
    matches!(
        expression,
        Expr::StringLiteral(_)
            | Expr::BytesLiteral(_)
            | Expr::NumberLiteral(_)
            | Expr::BooleanLiteral(_)
            | Expr::NoneLiteral(_)
            | Expr::EllipsisLiteral(_)
    )
}

pub(super) fn is_literal(expression: &Expr) -> bool {
    is_constant_literal(expression)
        || matches!(
            expression,
            Expr::List(_) | Expr::Tuple(_) | Expr::Dict(_) | Expr::Set(_)
        )
}

/// Type comments belong to the assignment even though Ruff leaves them outside its AST range.
fn assignment_has_type_comment(source: &Source, body: &[Stmt], index: usize) -> bool {
    let assignment = &body[index];
    let end = body
        .get(index + 1)
        .map_or_else(|| assignment.range().end(), Ranged::start);
    source
        .slice(ruff_text_size::TextRange::new(
            assignment.range().end(),
            end,
        ))
        .contains("# type:")
}
