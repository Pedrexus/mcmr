use ruff_python_ast::{ModModule, Stmt};

/// Return every statement in the module, including nested ones.
pub fn walk(module: &ModModule) -> Vec<&Stmt> {
    let mut collected = Vec::new();
    let mut pending: Vec<&Stmt> = module.body.iter().rev().collect();
    while let Some(statement) = pending.pop() {
        collected.push(statement);
        for block in blocks(statement) {
            pending.extend(block.iter().rev());
        }
    }
    collected
}

/// Return every statement one body holds, including the ones its blocks hold.
pub fn statements(body: &[Stmt]) -> Vec<&Stmt> {
    let mut collected = Vec::new();
    let mut pending: Vec<&Stmt> = body.iter().rev().collect();
    while let Some(statement) = pending.pop() {
        collected.push(statement);
        for block in blocks(statement) {
            pending.extend(block.iter().rev());
        }
    }
    collected
}

/// Return the statement blocks one statement owns.
pub fn blocks(statement: &Stmt) -> Vec<&[Stmt]> {
    match statement {
        Stmt::FunctionDef(item) => vec![&item.body],
        Stmt::ClassDef(item) => vec![&item.body],
        Stmt::If(item) => {
            let mut blocks: Vec<&[Stmt]> = vec![&item.body];
            blocks.extend(
                item.elif_else_clauses
                    .iter()
                    .map(|clause| clause.body.as_slice()),
            );
            blocks
        }
        Stmt::For(item) => vec![&item.body, &item.orelse],
        Stmt::While(item) => vec![&item.body, &item.orelse],
        Stmt::With(item) => vec![&item.body],
        Stmt::Try(item) => {
            let mut blocks: Vec<&[Stmt]> = vec![&item.body];
            blocks.extend(item.handlers.iter().map(|clause| match clause {
                ruff_python_ast::ExceptHandler::ExceptHandler(held) => held.body.as_slice(),
            }));
            blocks.extend([item.orelse.as_slice(), item.finalbody.as_slice()]);
            blocks
        }
        Stmt::Match(item) => item.cases.iter().map(|case| case.body.as_slice()).collect(),
        _ => Vec::new(),
    }
}
