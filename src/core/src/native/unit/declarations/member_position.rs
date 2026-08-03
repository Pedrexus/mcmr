use tree_sitter::Node as Syntax;

#[derive(Clone, Copy)]
pub(super) struct MemberPosition<'a> {
    pub(super) holder: Syntax<'a>,
    pub(super) member: Syntax<'a>,
}
