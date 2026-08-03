use crate::calls::{CallRecord, CallSite as TypedCallSite, Expression as CallExpression};
use crate::source::Source;
use crate::walk::{blocks, children, declared_name, expressions, qualified_name};
use ruff_python_ast::{Expr, ModModule, Stmt, StmtFunctionDef};
use ruff_text_size::Ranged;
use std::collections::BTreeSet;

mod collector;
mod expressions;
mod scope;

use collector::{CallCollector, ambiguous_imports};
use expressions::argument_value;
use scope::ScopeBindings;

pub(super) fn call_fact(source: &Source, module: &ModModule) -> CallRecord {
    let mut collector = CallCollector::new(source, ambiguous_imports(module));
    collect_calls(
        &mut collector,
        &module.body,
        &BTreeSet::new(),
        CallContext::default(),
    );
    let mut record = CallRecord::new(
        format!("calls:{}", source.relative),
        source.span(module.range()),
        "python",
    );
    record.calls = collector.calls;
    record.module_bindings = module.body.iter().filter_map(declared_name).collect();
    record
}

/// Conditions surrounding one call that are independent of name resolution.
#[derive(Clone, Copy, Default)]
struct CallContext {
    result_is_discarded: bool,
    is_decorator_factory: bool,
    enclosing_is_async: bool,
    is_class: bool,
}

fn collect_calls(
    collector: &mut CallCollector<'_>,
    body: &[Stmt],
    inherited_bindings: &BTreeSet<String>,
    context: CallContext,
) {
    let mut bindings = inherited_bindings.clone();
    bindings.extend(shadowing_bindings(body));
    for statement in body {
        collect_statement_calls(collector, statement, &bindings, context);
        collect_nested_calls(
            collector,
            statement,
            ScopeBindings {
                inherited: inherited_bindings,
                visible: &bindings,
            },
            context,
        );
    }
}

fn collect_statement_calls(
    collector: &mut CallCollector<'_>,
    statement: &Stmt,
    bindings: &BTreeSet<String>,
    context: CallContext,
) {
    let assigned = assigned_target(statement);
    for expression in expressions(statement) {
        collect_call_expressions(
            collector,
            expression,
            &assigned,
            CallContext {
                result_is_discarded: matches!(statement, Stmt::Expr(_)),
                is_decorator_factory: is_decorator(statement, expression),
                enclosing_is_async: context.enclosing_is_async,
                is_class: context.is_class,
            },
            bindings,
        );
    }
}

fn collect_nested_calls(
    collector: &mut CallCollector<'_>,
    statement: &Stmt,
    bindings: ScopeBindings<'_>,
    context: CallContext,
) {
    match statement {
        Stmt::FunctionDef(item) => {
            let inherited = if context.is_class {
                bindings.inherited
            } else {
                bindings.visible
            };
            collect_function_calls(collector, item, inherited);
        }
        Stmt::ClassDef(item) => collect_calls(
            collector,
            &item.body,
            bindings.visible,
            CallContext {
                is_class: true,
                ..CallContext::default()
            },
        ),
        _ => {
            for block in blocks(statement) {
                collect_calls(collector, block, bindings.visible, context);
            }
        }
    }
}

fn assigned_target(statement: &Stmt) -> String {
    match statement {
        Stmt::Assign(item) => item.targets.first().map(qualified_name),
        Stmt::AnnAssign(item) => Some(qualified_name(&item.target)),
        _ => None,
    }
    .unwrap_or_default()
}

fn is_decorator(statement: &Stmt, expression: &Expr) -> bool {
    match statement {
        Stmt::FunctionDef(item) => &item.decorator_list,
        Stmt::ClassDef(item) => &item.decorator_list,
        _ => return false,
    }
    .iter()
    .any(|decorator| decorator.expression.range() == expression.range())
}

fn collect_function_calls(
    collector: &mut CallCollector<'_>,
    item: &StmtFunctionDef,
    inherited_bindings: &BTreeSet<String>,
) {
    let mut bindings = inherited_bindings.clone();
    bindings.extend(
        item.parameters
            .iter()
            .map(|parameter| parameter.name().to_string()),
    );
    collect_calls(
        collector,
        &item.body,
        &bindings,
        CallContext {
            enclosing_is_async: item.is_async,
            ..CallContext::default()
        },
    );
}

fn collect_call_expressions(
    collector: &mut CallCollector<'_>,
    expression: &Expr,
    assigned_target: &str,
    context: CallContext,
    bindings: &BTreeSet<String>,
) {
    if let Expr::Call(item) = expression {
        let called = qualified_name(&item.func);
        let last = called.rsplit('.').next().unwrap_or(&called);
        let head = called.split('.').next().unwrap_or(&called);
        let arguments = item
            .arguments
            .args
            .iter()
            .map(|argument| argument_value(collector.source, argument))
            .collect::<Vec<_>>();
        let keyword_names = item
            .arguments
            .keywords
            .iter()
            .filter_map(|keyword| keyword.arg.as_ref().map(ToString::to_string))
            .collect::<Vec<_>>();
        let is_constructor = last.chars().next().is_some_and(char::is_uppercase);
        let is_shadowed = bindings.contains(head);
        let has_ambiguous_alias = collector.ambiguous.contains(head);
        let mut call = TypedCallSite::new(called, collector.source.node_of("call", item));
        call.arguments = arguments;
        call.keyword_names = keyword_names;
        call.receiver = receiver(collector.source, &item.func);
        call.assigned_target = assigned_target.to_string();
        call.result_is_discarded = context.result_is_discarded;
        call.callee = Some(collector.source.node_of("callee", item.func.as_ref()));
        call.is_constructor = is_constructor;
        call.is_decorator_factory = context.is_decorator_factory;
        call.is_shadowed = is_shadowed;
        call.has_ambiguous_alias = has_ambiguous_alias;
        call.has_starred_arguments = item
            .arguments
            .args
            .iter()
            .any(|argument| matches!(argument, Expr::Starred(_)));
        call.enclosing_is_async = context.enclosing_is_async;
        collector.calls.push(call);
    }
    for child in children(expression) {
        collect_call_expressions(
            collector,
            child,
            "",
            CallContext {
                enclosing_is_async: context.enclosing_is_async,
                ..CallContext::default()
            },
            bindings,
        );
    }
}

/// Return names one scope binds without importing them from somewhere else.
fn shadowing_bindings(body: &[Stmt]) -> BTreeSet<String> {
    let mut names = BTreeSet::new();
    let mut pending: Vec<&Stmt> = body.iter().collect();
    while let Some(statement) = pending.pop() {
        match statement {
            Stmt::Assign(item) => item
                .targets
                .iter()
                .for_each(|target| binding_names(target, &mut names)),
            Stmt::AnnAssign(item) => binding_names(&item.target, &mut names),
            Stmt::AugAssign(item) => binding_names(&item.target, &mut names),
            Stmt::For(item) => binding_names(&item.target, &mut names),
            Stmt::With(item) => item
                .items
                .iter()
                .filter_map(|entry| entry.optional_vars.as_deref())
                .for_each(|target| binding_names(target, &mut names)),
            Stmt::FunctionDef(item) => {
                names.insert(item.name.to_string());
                continue;
            }
            Stmt::ClassDef(item) => {
                names.insert(item.name.to_string());
                continue;
            }
            _ => {}
        }
        for block in blocks(statement) {
            pending.extend(block);
        }
    }
    names
}

/// Add every plain name one assignment target binds, including destructuring targets.
fn binding_names(target: &Expr, names: &mut BTreeSet<String>) {
    match target {
        Expr::Name(item) => {
            names.insert(item.id.to_string());
        }
        Expr::Tuple(item) => {
            for element in &item.elts {
                binding_names(element, names);
            }
        }
        Expr::List(item) => {
            for element in &item.elts {
                binding_names(element, names);
            }
        }
        Expr::Starred(item) => binding_names(&item.value, names),
        _ => {}
    }
}

fn receiver(source: &Source, callee: &Expr) -> Option<CallExpression> {
    match callee {
        Expr::Attribute(attribute) => Some(argument_value(source, &attribute.value)),
        _ => None,
    }
}
