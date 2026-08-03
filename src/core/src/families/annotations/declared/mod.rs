use super::role::AnnotationRole;
use ruff_python_ast::Expr;

/// One annotation and the declaration role it serves.
pub(super) struct DeclaredAnnotation<'expression> {
    pub(super) expression: &'expression Expr,
    pub(super) role: AnnotationRole,
    pub(super) is_external_boundary: bool,
}
