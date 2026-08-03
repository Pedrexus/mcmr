use super::super::collections::owned;
use crate::walk::{children, expressions};
use ruff_python_ast::{Expr, Parameters, Stmt};
use std::collections::BTreeSet;

pub(super) struct SetLoopContext<'a> {
    pub(super) function_body: &'a [Stmt],
    pub(super) external: &'a BTreeSet<String>,
}

/// Whether one scope can resolve a name to anything other than the builtin.
pub(super) fn scope_binds_name(
    parameters: Option<&Parameters>,
    body: &[Stmt],
    name: &str,
) -> bool {
    parameters.is_some_and(|held| {
        held.iter()
            .any(|parameter| parameter.name().as_str() == name)
    }) || owned(body)
        .into_iter()
        .any(|statement| statement_binds_name(statement, name))
}

fn statement_binds_name(statement: &Stmt, name: &str) -> bool {
    let direct = match statement {
        Stmt::FunctionDef(item) => item.name.as_str() == name,
        Stmt::ClassDef(item) => item.name.as_str() == name,
        Stmt::Assign(item) => item
            .targets
            .iter()
            .any(|target| target_binds_name(target, name)),
        Stmt::AnnAssign(item) => target_binds_name(&item.target, name),
        Stmt::AugAssign(item) => target_binds_name(&item.target, name),
        Stmt::Delete(item) => item
            .targets
            .iter()
            .any(|target| target_binds_name(target, name)),
        Stmt::TypeAlias(item) => target_binds_name(&item.name, name),
        Stmt::For(item) => target_binds_name(&item.target, name),
        Stmt::With(item) => item.items.iter().any(|entry| {
            entry
                .optional_vars
                .as_deref()
                .is_some_and(|target| target_binds_name(target, name))
        }),
        Stmt::Import(item) => item
            .names
            .iter()
            .any(|alias| import_binds_name(alias, name)),
        Stmt::ImportFrom(item) => item
            .names
            .iter()
            .any(|alias| alias.name.as_str() == "*" || from_import_bound_name(alias) == name),
        Stmt::Global(item) => item.names.iter().any(|held| held.as_str() == name),
        Stmt::Nonlocal(item) => item.names.iter().any(|held| held.as_str() == name),
        Stmt::Try(item) => item.handlers.iter().any(|handler| {
            let ruff_python_ast::ExceptHandler::ExceptHandler(clause) = handler;
            clause
                .name
                .as_ref()
                .is_some_and(|held| held.as_str() == name)
        }),
        Stmt::Match(item) => item
            .cases
            .iter()
            .any(|case| pattern_binds_name(&case.pattern, name)),
        _ => false,
    };
    direct
        || complete_stated_expressions(statement)
            .into_iter()
            .any(|expression| named_expression_binds_name(expression, name))
}

/// Return every directly evaluated expression omitted by the shared shallow walker.
pub(in crate::families) fn complete_statement_expressions(statement: &Stmt) -> Vec<&Expr> {
    let mut found = expressions(statement);
    match statement {
        Stmt::Raise(item) => found.extend(item.cause.iter().map(AsRef::as_ref)),
        Stmt::Assert(item) => found.extend(item.msg.iter().map(AsRef::as_ref)),
        Stmt::Try(item) => found.extend(item.handlers.iter().filter_map(|handler| {
            let ruff_python_ast::ExceptHandler::ExceptHandler(clause) = handler;
            clause.type_.as_deref()
        })),
        Stmt::Match(item) => {
            found.push(item.subject.as_ref());
            found.extend(item.cases.iter().filter_map(|case| case.guard.as_deref()));
        }
        Stmt::ClassDef(item) => found.extend(
            item.arguments
                .iter()
                .flat_map(|arguments| arguments.keywords.iter())
                .map(|keyword| &keyword.value),
        ),
        _ => {}
    }
    found
}

pub(super) fn complete_stated_expressions(statement: &Stmt) -> Vec<&Expr> {
    let mut found = complete_statement_expressions(statement);
    match statement {
        Stmt::Assign(item) => found.extend(item.targets.iter()),
        Stmt::AnnAssign(item) => found.push(item.target.as_ref()),
        Stmt::AugAssign(item) => found.push(item.target.as_ref()),
        Stmt::With(item) => found.extend(
            item.items
                .iter()
                .filter_map(|entry| entry.optional_vars.as_deref()),
        ),
        Stmt::TypeAlias(item) => found.push(item.name.as_ref()),
        _ => {}
    }
    found
}

fn target_binds_name(target: &Expr, name: &str) -> bool {
    match target {
        Expr::Name(item) => item.id.as_str() == name,
        Expr::List(item) => item.elts.iter().any(|held| target_binds_name(held, name)),
        Expr::Tuple(item) => item.elts.iter().any(|held| target_binds_name(held, name)),
        Expr::Starred(item) => target_binds_name(&item.value, name),
        _ => false,
    }
}

fn named_expression_binds_name(expression: &Expr, name: &str) -> bool {
    matches!(expression, Expr::Named(item) if target_binds_name(&item.target, name))
        || children(expression)
            .into_iter()
            .any(|child| named_expression_binds_name(child, name))
}

fn import_binds_name(alias: &ruff_python_ast::Alias, name: &str) -> bool {
    import_bound_name(alias) == name
}

fn import_bound_name(alias: &ruff_python_ast::Alias) -> &str {
    alias.asname.as_ref().map_or_else(
        || alias.name.as_str().split('.').next().unwrap_or_default(),
        |held| held.as_str(),
    )
}

fn from_import_bound_name(alias: &ruff_python_ast::Alias) -> &str {
    alias
        .asname
        .as_ref()
        .map_or_else(|| alias.name.as_str(), |held| held.as_str())
}

fn pattern_binds_name(pattern: &ruff_python_ast::Pattern, name: &str) -> bool {
    use ruff_python_ast::Pattern;
    match pattern {
        Pattern::MatchSequence(item) => item
            .patterns
            .iter()
            .any(|held| pattern_binds_name(held, name)),
        Pattern::MatchMapping(item) => {
            item.rest.as_ref().is_some_and(|held| held.as_str() == name)
                || item
                    .patterns
                    .iter()
                    .any(|held| pattern_binds_name(held, name))
        }
        Pattern::MatchClass(item) => item
            .arguments
            .patterns
            .iter()
            .chain(item.arguments.keywords.iter().map(|held| &held.pattern))
            .any(|held| pattern_binds_name(held, name)),
        Pattern::MatchStar(item) => item.name.as_ref().is_some_and(|held| held.as_str() == name),
        Pattern::MatchAs(item) => {
            item.name.as_ref().is_some_and(|held| held.as_str() == name)
                || item
                    .pattern
                    .as_deref()
                    .is_some_and(|held| pattern_binds_name(held, name))
        }
        Pattern::MatchOr(item) => item
            .patterns
            .iter()
            .any(|held| pattern_binds_name(held, name)),
        Pattern::MatchValue(_) | Pattern::MatchSingleton(_) => false,
    }
}
