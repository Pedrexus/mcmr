use tree_sitter::Node as Syntax;

#[derive(Clone, Copy)]
pub(super) struct TypeBody<'a> {
    pub(super) holder: Syntax<'a>,
    pub(super) body: Syntax<'a>,
}
