#[derive(Clone, Copy)]
pub(super) struct CallableIdentity<'callable> {
    pub(super) owner: &'callable str,
    pub(super) qualname: &'callable str,
}
