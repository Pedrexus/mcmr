use ruff_python_ast::Stmt;

#[derive(Clone, Copy)]
pub(super) enum QueryScope {
    OutsideLoop,
    InsideLoop,
}

impl QueryScope {
    pub(super) fn is_inside_loop(self) -> bool {
        matches!(self, Self::InsideLoop)
    }

    pub(super) fn nested(self, statement: &Stmt) -> Self {
        match statement {
            Stmt::For(_) | Stmt::While(_) => Self::InsideLoop,
            Stmt::FunctionDef(_) | Stmt::ClassDef(_) => Self::OutsideLoop,
            _ => self,
        }
    }
}
