#[derive(Clone, Copy)]
pub(crate) struct ClassAddress<'repository> {
    pub(crate) path: &'repository str,
    pub(crate) name: &'repository str,
}
