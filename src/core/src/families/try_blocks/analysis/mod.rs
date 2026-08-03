use super::super::comprehensions::complete_statement_expressions;
use crate::walk::{blocks, children};
use ruff_python_ast::{Expr, Stmt};

/// Whether a statement executes one operation from the rule's explicit raising set.
pub(super) fn statement_contains_raising_operation(statement: &Stmt) -> bool {
    if matches!(
        statement,
        Stmt::Import(_)
            | Stmt::ImportFrom(_)
            | Stmt::Assert(_)
            | Stmt::Raise(_)
            | Stmt::For(_)
            | Stmt::With(_)
            | Stmt::AugAssign(_)
    ) {
        return true;
    }
    let direct = match statement {
        Stmt::FunctionDef(item) => item
            .decorator_list
            .iter()
            .map(|decorator| &decorator.expression)
            .chain(
                item.parameters
                    .iter_non_variadic_params()
                    .filter_map(|parameter| parameter.default()),
            )
            .any(expression_contains_raising_operation),
        Stmt::ClassDef(item) => item
            .decorator_list
            .iter()
            .map(|decorator| &decorator.expression)
            .chain(
                item.arguments
                    .iter()
                    .flat_map(|arguments| arguments.args.iter()),
            )
            .chain(
                item.arguments
                    .iter()
                    .flat_map(|arguments| arguments.keywords.iter())
                    .map(|keyword| &keyword.value),
            )
            .any(expression_contains_raising_operation),
        _ => complete_statement_expressions(statement)
            .into_iter()
            .any(expression_contains_raising_operation),
    };
    if direct || matches!(statement, Stmt::FunctionDef(_) | Stmt::ClassDef(_)) {
        return direct;
    }
    blocks(statement)
        .into_iter()
        .flatten()
        .any(statement_contains_raising_operation)
}

fn expression_contains_raising_operation(expression: &Expr) -> bool {
    let raises_directly = match expression {
        Expr::Call(_)
        | Expr::Attribute(_)
        | Expr::Subscript(_)
        | Expr::BinOp(_)
        | Expr::Compare(_)
        | Expr::Await(_)
        | Expr::ListComp(_)
        | Expr::SetComp(_)
        | Expr::DictComp(_)
        | Expr::Generator(_)
        | Expr::YieldFrom(_) => true,
        Expr::UnaryOp(item) => item.op != ruff_python_ast::UnaryOp::Not,
        _ => false,
    };
    if raises_directly {
        return true;
    }
    if let Expr::Lambda(item) = expression {
        return item.parameters.iter().any(|parameters| {
            parameters
                .iter_non_variadic_params()
                .filter_map(|parameter| parameter.default())
                .any(expression_contains_raising_operation)
        });
    }
    children(expression)
        .into_iter()
        .any(expression_contains_raising_operation)
}

/// Count each executable statement, descending through compounds but not through new scopes.
fn executable_statement_count(body: &[Stmt]) -> usize {
    body.iter().map(executable_statement_size).sum()
}

fn executable_statement_size(statement: &Stmt) -> usize {
    if matches!(
        statement,
        Stmt::FunctionDef(_) | Stmt::ClassDef(_) | Stmt::Try(_)
    ) {
        return 0;
    }
    1 + blocks(statement)
        .into_iter()
        .map(executable_statement_count)
        .sum::<usize>()
}

pub(super) fn try_clause_statement_counts(item: &ruff_python_ast::StmtTry) -> Vec<usize> {
    let mut counts = vec![executable_statement_count(&item.body)];
    counts.extend(item.handlers.iter().map(|handler| {
        let ruff_python_ast::ExceptHandler::ExceptHandler(clause) = handler;
        executable_statement_count(&clause.body)
    }));
    if !item.orelse.is_empty() {
        counts.push(executable_statement_count(&item.orelse));
    }
    if !item.finalbody.is_empty() {
        counts.push(executable_statement_count(&item.finalbody));
    }
    counts
}
