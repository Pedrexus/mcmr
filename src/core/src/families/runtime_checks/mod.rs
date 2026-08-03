use super::parameters::Uses;
use crate::walk::{children, expressions, qualified_name, walk};
use ruff_python_ast::{Expr, ModModule, Stmt};
use serde_json::{Value, json};

/// Every isinstance check one file makes, with the operations the block it guards performs.
///
/// What a check stands in for is only visible in what it protects, so the guarded block travels
/// with it. A check written anywhere but a branch test guards nothing this file can point at, and
/// says so by naming no operation rather than by being left out.
pub fn runtime_checks(module: &ModModule) -> Value {
    let mut checks = Vec::new();
    for statement in walk(module) {
        match statement {
            Stmt::If(item) => {
                let guarded = Guard {
                    body: &item.body,
                    alone: item.body.len() == 1 && item.elif_else_clauses.is_empty(),
                };
                collect_checks(&item.test, Some(&guarded), &mut checks);
            }
            _ => {
                for expression in expressions(statement) {
                    collect_checks(expression, None, &mut checks);
                }
            }
        }
    }
    json!({"checks": checks})
}

/// The block one branch protects, and whether protecting it is all the branch does.
struct Guard<'source> {
    body: &'source [Stmt],
    alone: bool,
}

fn collect_checks(expression: &Expr, guard: Option<&Guard>, checks: &mut Vec<Value>) {
    if let Expr::Call(item) = expression
        && qualified_name(&item.func) == "isinstance"
        && item.arguments.args.len() == 2
    {
        let subject = qualified_name(&item.arguments.args[0]);
        let performed = guard
            .map(|held| guarded_operations(held.body, &subject))
            .unwrap_or_default();
        checks.push(json!({
            "concrete_type": qualified_name(&item.arguments.args[1]),
            "guarded_operations": performed,
            "can_use_eafp": guard.is_some_and(|held| held.alone),
        }));
    }
    for child in children(expression) {
        collect_checks(child, guard, checks);
    }
}

/// Return the operations one guarded block performs on the value the check narrowed.
fn guarded_operations(body: &[Stmt], subject: &str) -> Vec<String> {
    let mut uses = Uses::default();
    uses.read_body(body, subject);
    let mut found: Vec<String> = uses.operations.into_iter().collect();
    found.extend(uses.attributes);
    found.sort();
    found.dedup();
    found
}
