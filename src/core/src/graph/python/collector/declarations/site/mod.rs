use ruff_python_ast::Stmt;

#[derive(Clone, Copy)]
pub(super) struct DeclarationSite<'a> {
    pub(super) id: &'a str,
    pub(super) qualname: &'a str,
    pub(super) statement: &'a Stmt,
}
