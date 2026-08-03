use ruff_python_ast::Expr;

pub(super) struct SetCandidate<'expression> {
    pub(super) name: &'expression str,
    pub(super) is_annotated: bool,
    pub(super) element: &'expression Expr,
    pub(super) conditions: Vec<&'expression Expr>,
}
