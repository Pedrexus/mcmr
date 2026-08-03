use crate::functions::ControlIncrement;
use ruff_python_ast::Stmt;

pub(crate) fn control_increments(body: &[Stmt], depth: usize) -> Vec<ControlIncrement> {
    let mut increments = Vec::new();
    for statement in body {
        let (kind, nested) = control_shape(statement);
        if let Some(kind) = kind {
            increments.push(ControlIncrement::new(kind, depth));
        }
        let inner = if kind.is_some() { depth + 1 } else { depth };
        for block in nested {
            increments.extend(control_increments(block, inner));
        }
        increments.extend(branch_increments(
            statement,
            ControlDepth {
                current: depth,
                nested: inner,
            },
        ));
    }
    increments
}

fn control_shape(statement: &Stmt) -> (Option<&str>, Vec<&[Stmt]>) {
    match statement {
        Stmt::If(item) => (Some("conditional"), vec![&item.body]),
        Stmt::For(item) => (Some("loop"), vec![&item.body, &item.orelse]),
        Stmt::While(item) => (Some("loop"), vec![&item.body, &item.orelse]),
        Stmt::With(item) => (None, vec![&item.body]),
        Stmt::Match(_) => (Some("switch"), vec![]),
        Stmt::Try(item) => (
            Some("catch"),
            vec![&item.body, &item.orelse, &item.finalbody],
        ),
        Stmt::Break(_) | Stmt::Continue(_) => (Some("jump"), vec![]),
        _ => (None, vec![]),
    }
}

#[derive(Clone, Copy)]
struct ControlDepth {
    current: usize,
    nested: usize,
}

fn branch_increments(statement: &Stmt, depth: ControlDepth) -> Vec<ControlIncrement> {
    let mut increments = Vec::new();
    match statement {
        Stmt::If(item) => {
            for clause in &item.elif_else_clauses {
                increments.push(ControlIncrement::new("alternative", depth.current));
                increments.extend(control_increments(&clause.body, depth.nested));
            }
        }
        Stmt::Match(item) => {
            for case in &item.cases {
                increments.extend(control_increments(&case.body, depth.nested));
            }
        }
        Stmt::Try(item) => {
            for handler in &item.handlers {
                let ruff_python_ast::ExceptHandler::ExceptHandler(clause) = handler;
                increments.extend(control_increments(&clause.body, depth.nested));
            }
        }
        _ => {}
    }
    increments
}
