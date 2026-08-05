use super::super::collections::stated;
use super::super::waivers::days_since;
use super::structure::{conditional_count, declared_tests, literal_shape, owned_statements};
use crate::source::Source;
use crate::walk::{children, docstring, qualified_name};
use ruff_python_ast::{Expr, ModModule, Number, Stmt};
use serde_json::{Value, json};
use std::collections::BTreeSet;

use fixtures::{fixture_parameters, reached_fixtures};
use generated::{generated_case_sources, generated_parametrization_count};

mod fixtures;
mod generated;

/// Every test one file declares, with the fixtures, marks, and module state each reaches.
///
/// Whether a runner collects a callable is read from where it sits rather than from its name. A
/// module-level `test` callable is collected, one declared in a `Test` class with no initializer
/// is collected as a method, and one nested inside another callable is never reached at all.
pub fn test_functions(source: &Source, module: &ModModule) -> Value {
    let fixtures = fixture_parameters(module);
    let state = module_state(module);
    let generated = generated_case_sources(module);
    let mut tests = Vec::new();
    for (item, collected) in declared_tests(&module.body) {
        let (body_shape, literal_values) = literal_shape(source, &item.body);
        let requested: Vec<String> = item
            .parameters
            .iter()
            .map(|parameter| parameter.name().to_string())
            .collect();
        tests.push(json!({
            "name": item.name.to_string(),
            "path": source.relative.clone(),
            "node": source.node_of("test", item),
            "is_collected": collected,
            "is_async": item.is_async,
            "requested_fixture_names": requested.clone(),
            "marks": item
                .decorator_list
                .iter()
                .map(|decorator| qualified_name(&decorator.expression))
                .collect::<Vec<_>>(),
            "calls": test_calls(source, &item.body),
            "body_shape": body_shape,
            "literal_values": literal_values,
            "assertion_shapes": assertion_shapes(source, &item.body),
            "owned_conditional_count": conditional_count(&item.body),
            "owned_statement_count": owned_statements(&item.body).len()
                - usize::from(docstring(&item.body).is_some()),
            "module_state_mutation_count": module_state_mutations(&item.body, &state),
            "parametrized_range_sizes": parametrized_sizes(item),
            "generated_parametrization_count": generated_parametrization_count(item, &generated),
            "fixture_names": reached_fixtures(&requested, &fixtures),
        }));
    }
    let quarantined_tests = declared_tests(&module.body)
        .into_iter()
        .filter_map(|(item, collected)| collected.then_some(item))
        .flat_map(quarantines)
        .collect::<Vec<_>>();
    json!({"tests": tests, "quarantined_tests": quarantined_tests})
}

fn assertion_shapes(source: &Source, body: &[Stmt]) -> Vec<String> {
    owned_statements(body)
        .into_iter()
        .filter(|statement| matches!(statement, Stmt::Assert(_)))
        .map(|statement| literal_shape(source, std::slice::from_ref(statement)).0)
        .collect()
}

/// Return explicit flaky-test quarantines and the lifecycle metadata their marker states.
fn quarantines(item: &ruff_python_ast::StmtFunctionDef) -> Vec<Value> {
    item.decorator_list
        .iter()
        .filter(|decorator| {
            matches!(
                qualified_name(&decorator.expression).rsplit('.').next(),
                Some("flaky" | "quarantine" | "quarantined")
            )
        })
        .map(|decorator| {
            let call = match &decorator.expression {
                Expr::Call(call) => Some(call),
                _ => None,
            };
            let keyword = |wanted: &str| {
                call.and_then(|held| {
                    held.arguments.keywords.iter().find_map(|keyword| {
                        keyword
                            .arg
                            .as_ref()
                            .is_some_and(|name| name == wanted)
                            .then_some(&keyword.value)
                    })
                })
            };
            let text = |wanted: &str| match keyword(wanted) {
                Some(Expr::StringLiteral(value)) => value.value.to_str().to_string(),
                _ => String::new(),
            };
            let age_days = match keyword("age_days") {
                Some(Expr::NumberLiteral(value)) => match &value.value {
                    Number::Int(days) => days.as_i64().and_then(|held| usize::try_from(held).ok()),
                    _ => None,
                },
                _ => {
                    let since = text("since");
                    (!since.is_empty())
                        .then(|| days_since(&since))
                        .flatten()
                        .and_then(|held| usize::try_from(held).ok())
                }
            };
            let owner = text("owner");
            let remediation = text("remediation");
            let recurred_after_repair = matches!(
                keyword("recurred_after_repair"),
                Some(Expr::BooleanLiteral(value)) if value.value
            );
            json!({
                "name": item.name.to_string(),
                "age_days": age_days,
                "owner": owner,
                "has_remediation_evidence": !remediation.trim().is_empty(),
                "recurred_after_repair": recurred_after_repair,
            })
        })
        .collect()
}

/// Return every module-scope name one file binds, which is the state its tests can share.
fn module_state(module: &ModModule) -> BTreeSet<String> {
    module
        .body
        .iter()
        .flat_map(|statement| match statement {
            Stmt::Assign(item) => item.targets.iter().collect::<Vec<_>>(),
            Stmt::AnnAssign(item) => vec![item.target.as_ref()],
            _ => Vec::new(),
        })
        .filter_map(|target| match target {
            Expr::Name(name) => Some(name.id.to_string()),
            _ => None,
        })
        .collect()
}

/// Return how many times one test writes to state its module holds.
///
/// Rebinding through `global`, mutating a shared collection in place, and writing through a
/// subscript all outlive the test that did them, which is what makes the next test order dependent.
fn module_state_mutations(body: &[Stmt], state: &BTreeSet<String>) -> usize {
    const MUTATING: &[&str] = &[
        "append",
        "extend",
        "insert",
        "pop",
        "remove",
        "clear",
        "update",
        "add",
        "sort",
        "setdefault",
        "popitem",
        "discard",
    ];
    let mut count = 0;
    for statement in owned_statements(body) {
        match statement {
            Stmt::Global(item) => count += item.names.len(),
            Stmt::Assign(item) => {
                count += item
                    .targets
                    .iter()
                    .filter(|target| writes_state(target, state))
                    .count();
            }
            Stmt::AugAssign(item) => count += usize::from(writes_state(&item.target, state)),
            _ => {}
        }
        for expression in stated(statement) {
            count += mutating_calls(expression, state, MUTATING);
        }
    }
    count
}

fn writes_state(target: &Expr, state: &BTreeSet<String>) -> bool {
    match target {
        Expr::Subscript(item) => matches!(item.value.as_ref(), Expr::Name(name)
            if state.contains(name.id.as_str())),
        Expr::Attribute(item) => matches!(item.value.as_ref(), Expr::Name(name)
            if state.contains(name.id.as_str())),
        _ => false,
    }
}

fn mutating_calls(expression: &Expr, state: &BTreeSet<String>, mutating: &[&str]) -> usize {
    let here = match expression {
        Expr::Call(item) => match item.func.as_ref() {
            Expr::Attribute(method) => usize::from(
                mutating.contains(&method.attr.as_str())
                    && matches!(method.value.as_ref(), Expr::Name(name)
                        if state.contains(name.id.as_str())),
            ),
            _ => 0,
        },
        _ => 0,
    };
    here + children(expression)
        .into_iter()
        .map(|child| mutating_calls(child, state, mutating))
        .sum::<usize>()
}

/// Return how many cases each static `range` parametrization one test carries states.
fn parametrized_sizes(item: &ruff_python_ast::StmtFunctionDef) -> Vec<usize> {
    item.decorator_list
        .iter()
        .filter(|decorator| qualified_name(&decorator.expression).ends_with("parametrize"))
        .filter_map(|decorator| match &decorator.expression {
            Expr::Call(call) => call.arguments.args.get(1),
            _ => None,
        })
        .filter_map(|cases| match cases {
            Expr::Call(item) if qualified_name(&item.func) == "range" => range_size(item),
            _ => None,
        })
        .collect()
}

/// Return how many values one `range` call states, when every bound is written out.
fn range_size(call: &ruff_python_ast::ExprCall) -> Option<usize> {
    let bounds: Vec<i64> = call
        .arguments
        .args
        .iter()
        .filter_map(|argument| match argument {
            Expr::NumberLiteral(item) => match &item.value {
                ruff_python_ast::Number::Int(held) => held.as_i64(),
                _ => None,
            },
            _ => None,
        })
        .collect();
    match bounds.as_slice() {
        [stop] => usize::try_from(*stop).ok(),
        [start, stop] => usize::try_from(stop - start).ok(),
        _ => None,
    }
}

/// Return every call one test body makes, addressed so a rule can point at it.
///
/// Name resolution is joined from the repository graph after extraction, so this syntax pass
/// keeps only the location and spelling that the test rule reads.
fn test_calls(source: &Source, body: &[Stmt]) -> Vec<Value> {
    let mut found = Vec::new();
    for statement in owned_statements(body) {
        for expression in stated(statement) {
            collect_test_calls(source, expression, &mut found);
        }
    }
    found
}

fn collect_test_calls(source: &Source, expression: &Expr, found: &mut Vec<Value>) {
    if let Expr::Call(item) = expression {
        let called = qualified_name(&item.func);
        found.push(json!({
            "qualified_name": called,
            "path": source.relative.clone(),
            "node": source.node_of("call", item),
        }));
    }
    for child in children(expression) {
        collect_test_calls(source, child, found);
    }
}
