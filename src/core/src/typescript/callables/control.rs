use crate::functions::ControlIncrement;
use oxc_ast::ast::{FunctionBody, Statement};

/// Return how many collected structures are plain conditions.
pub(in crate::typescript) fn conditionals(increments: &[ControlIncrement]) -> usize {
    increments
        .iter()
        .filter(|increment| increment.kind == "conditional")
        .count()
}

/// Collect the control structures in one body and their visible nesting depth.
pub(in crate::typescript) fn control_increments(
    body: Option<&FunctionBody>,
) -> Vec<ControlIncrement> {
    let mut found = Control::default();
    found.statements(body.iter().flat_map(|held| held.statements.iter()));
    found.increments
}

#[derive(Default)]
struct Control {
    depth: usize,
    increments: Vec<ControlIncrement>,
}

impl Control {
    fn alternative(&mut self, otherwise: &Statement) {
        self.record("alternative");
        match otherwise {
            Statement::IfStatement(chained) => {
                self.inside(&chained.consequent);
                if let Some(next) = &chained.alternate {
                    self.alternative(next);
                }
            }
            held => self.inside(held),
        }
    }

    fn if_statement(&mut self, statement: &oxc_ast::ast::IfStatement<'_>) {
        self.opens("conditional", &statement.consequent);
        if let Some(otherwise) = &statement.alternate {
            self.alternative(otherwise);
        }
    }

    fn inside(&mut self, held: &Statement) {
        self.depth += 1;
        self.read(held);
        self.depth -= 1;
    }

    fn opens(&mut self, kind: &str, body: &Statement) {
        self.record(kind);
        self.inside(body);
    }

    fn read(&mut self, statement: &Statement) {
        match statement {
            Statement::IfStatement(held) => self.if_statement(held),
            Statement::ForStatement(held) => self.opens("loop", &held.body),
            Statement::ForInStatement(held) => self.opens("loop", &held.body),
            Statement::ForOfStatement(held) => self.opens("loop", &held.body),
            Statement::WhileStatement(held) => self.opens("loop", &held.body),
            Statement::DoWhileStatement(held) => self.opens("loop", &held.body),
            Statement::SwitchStatement(held) => self.switch_statement(held),
            Statement::TryStatement(held) => self.try_statement(held),
            Statement::BlockStatement(held) => self.statements(&held.body),
            Statement::LabeledStatement(held) => self.read(&held.body),
            Statement::WithStatement(held) => self.read(&held.body),
            _ => {}
        }
    }

    fn record(&mut self, kind: &str) {
        self.increments
            .push(ControlIncrement::new(kind, self.depth));
    }

    fn statements<'ast>(&mut self, statements: impl IntoIterator<Item = &'ast Statement<'ast>>) {
        for statement in statements {
            self.read(statement);
        }
    }

    fn switch_statement(&mut self, statement: &oxc_ast::ast::SwitchStatement<'_>) {
        self.record("switch");
        self.depth += 1;
        self.statements(statement.cases.iter().flat_map(|case| &case.consequent));
        self.depth -= 1;
    }

    fn try_statement(&mut self, statement: &oxc_ast::ast::TryStatement<'_>) {
        self.record("catch");
        self.depth += 1;
        self.statements(&statement.block.body);
        self.statements(
            statement
                .handler
                .iter()
                .flat_map(|clause| &clause.body.body),
        );
        self.statements(statement.finalizer.iter().flat_map(|block| &block.body));
        self.depth -= 1;
    }
}
