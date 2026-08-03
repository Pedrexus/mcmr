#[derive(Clone, Copy)]
pub(super) struct DeclarationIdentity<'declaration> {
    pub(super) qualname: &'declaration str,
    pub(super) kind: &'declaration str,
}
