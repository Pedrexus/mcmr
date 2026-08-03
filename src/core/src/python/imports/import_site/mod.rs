use ruff_python_ast::Stmt;

/// One import statement with the evidence needed by every binding it creates.
#[derive(Clone, Copy)]
pub(super) struct ImportSite<'statement> {
    pub(super) statement: &'statement Stmt,
    pub(super) module: &'statement str,
    pub(super) level: u32,
    pub(super) binding_count: usize,
    pub(super) is_guarded: bool,
    pub(super) is_type_only: bool,
}
