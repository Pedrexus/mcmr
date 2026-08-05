use super::context::{SetLoopContext, complete_stated_expressions};
use crate::source::Source;
use crate::walk::{blocks, children, qualified_name};
use ruff_python_ast::{Expr, Stmt};
use ruff_text_size::{Ranged, TextRange, TextSize};
use serde_json::{Value, json};
use std::collections::BTreeSet;

struct SetCandidate {
    name: String,
    is_annotated: bool,
    element: TextRange,
    conditions: Vec<TextRange>,
}

pub(super) fn set_loop_candidate(
    source: &Source,
    pair: &[Stmt],
    context: &SetLoopContext<'_>,
) -> Option<Value> {
    let [initialization_statement, Stmt::For(loop_statement)] = pair else {
        return None;
    };
    let candidate = safe_candidate(initialization_statement, loop_statement, context)?;
    let replacement_range = replacement_range(source, initialization_statement, loop_statement);
    let edit_is_safe = !candidate.is_annotated && !source.slice(replacement_range).contains('#');
    Some(json!({
        "name": candidate.name,
        "has_unshadowed_set_initialization": true,
        "loop_is_synchronous": true,
        "only_effect_is_add": true,
        "conditional_count": candidate.conditions.len(),
        "has_else": false,
        "initialization": source.node_of("statement", initialization_statement),
        "loop": source.node_of("statement", &pair[1]),
        "element": edit_is_safe.then(|| source.node("expression", candidate.element)),
        "target": source.node_of("expression", loop_statement.target.as_ref()),
        "iterable": source.node_of("expression", loop_statement.iter.as_ref()),
        "conditions": candidate.conditions.iter()
            .map(|condition| source.node("expression", *condition))
            .collect::<Vec<_>>(),
    }))
}

fn safe_candidate(
    initialization: &Stmt,
    loop_statement: &ruff_python_ast::StmtFor,
    context: &SetLoopContext<'_>,
) -> Option<SetCandidate> {
    let (name, is_annotated) = set_initialization(initialization)?;
    if context.external.contains(name)
        || loop_statement.is_async
        || !loop_statement.orelse.is_empty()
    {
        return None;
    }
    let (body, conditions) = match loop_statement.body.as_slice() {
        [Stmt::If(branch)] if branch.elif_else_clauses.is_empty() => {
            (branch.body.as_slice(), vec![branch.test.as_ref()])
        }
        held => (held, Vec::new()),
    };
    let [Stmt::Expr(statement)] = body else {
        return None;
    };
    let Expr::Call(call) = statement.value.as_ref() else {
        return None;
    };
    if qualified_name(&call.func) != format!("{name}.add")
        || call.arguments.args.len() != 1
        || !call.arguments.keywords.is_empty()
    {
        return None;
    }
    let element = call.arguments.args.first()?;
    let target_names = bound_target_names(&loop_statement.target);
    (!target_names.is_empty()
        && !target_names.contains(name)
        && !loop_bindings_are_read_elsewhere(
            context.function_body,
            &target_names,
            loop_statement.range,
        )
        && !expression_has_comprehension_hazard(&loop_statement.iter)
        && !expression_has_comprehension_hazard(element)
        && !expression_reads_name(element, name)
        && conditions
            .iter()
            .all(|condition| !expression_has_comprehension_hazard(condition)))
    .then_some(SetCandidate {
        name: name.to_string(),
        is_annotated,
        element: element.range(),
        conditions: conditions.into_iter().map(Ranged::range).collect(),
    })
}

fn replacement_range(
    source: &Source,
    initialization: &Stmt,
    loop_statement: &ruff_python_ast::StmtFor,
) -> TextRange {
    let loop_end = usize::from(loop_statement.range.end());
    let line_end = source.text[loop_end..]
        .find('\n')
        .map_or(source.text.len(), |offset| loop_end + offset);
    TextRange::new(
        initialization.range().start(),
        TextSize::try_from(line_end).expect("a source offset fits Ruff's index"),
    )
}

fn set_initialization(statement: &Stmt) -> Option<(&str, bool)> {
    match statement {
        Stmt::Assign(item) => {
            let [Expr::Name(target)] = item.targets.as_slice() else {
                return None;
            };
            is_empty_set(&item.value).then_some((target.id.as_str(), false))
        }
        Stmt::AnnAssign(item) => {
            let Expr::Name(target) = item.target.as_ref() else {
                return None;
            };
            item.value
                .as_deref()
                .is_some_and(is_empty_set)
                .then_some((target.id.as_str(), true))
        }
        _ => None,
    }
}

fn is_empty_set(value: &Expr) -> bool {
    matches!(value, Expr::Call(call)
        if qualified_name(&call.func) == "set"
            && call.arguments.args.is_empty()
            && call.arguments.keywords.is_empty())
}

fn expression_has_comprehension_hazard(expression: &Expr) -> bool {
    matches!(
        expression,
        Expr::Named(_) | Expr::Await(_) | Expr::Yield(_) | Expr::YieldFrom(_)
    ) || children(expression)
        .into_iter()
        .any(expression_has_comprehension_hazard)
}

fn expression_reads_name(expression: &Expr, name: &str) -> bool {
    matches!(expression, Expr::Name(item)
        if item.id.as_str() == name && item.ctx.is_load())
        || children(expression)
            .into_iter()
            .any(|child| expression_reads_name(child, name))
}

fn bound_target_names(target: &Expr) -> BTreeSet<String> {
    match target {
        Expr::Name(item) => BTreeSet::from([item.id.to_string()]),
        Expr::List(item) => item.elts.iter().flat_map(bound_target_names).collect(),
        Expr::Tuple(item) => item.elts.iter().flat_map(bound_target_names).collect(),
        Expr::Starred(item) => bound_target_names(&item.value),
        _ => BTreeSet::new(),
    }
}

fn loop_bindings_are_read_elsewhere(
    body: &[Stmt],
    names: &BTreeSet<String>,
    loop_range: TextRange,
) -> bool {
    body.iter()
        .any(|statement| statement_reads_names_outside(statement, names, loop_range))
}

fn statement_reads_names_outside(
    statement: &Stmt,
    names: &BTreeSet<String>,
    excluded: TextRange,
) -> bool {
    if statement.range() == excluded {
        return false;
    }
    complete_stated_expressions(statement)
        .into_iter()
        .any(|expression| {
            names
                .iter()
                .any(|name| expression_reads_name(expression, name))
        })
        || blocks(statement)
            .into_iter()
            .flatten()
            .any(|nested| statement_reads_names_outside(nested, names, excluded))
}
