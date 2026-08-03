#[derive(Clone, Copy)]
pub(super) struct BindingOrigin<'binding> {
    pub(super) name: &'binding str,
    pub(super) module: &'binding str,
}
