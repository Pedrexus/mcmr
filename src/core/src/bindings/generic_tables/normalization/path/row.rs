#[derive(Clone, Copy)]
pub(crate) struct RowPath<'a> {
    pub(crate) scalar: &'a str,
    pub(crate) relation: &'a str,
    pub(crate) parent_id: &'a str,
}
