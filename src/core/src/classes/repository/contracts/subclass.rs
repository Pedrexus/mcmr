use super::super::super::model::Identity;

#[derive(Clone, Copy)]
pub(crate) struct SubclassReference<'repository> {
    pub(crate) held: &'repository Identity,
    pub(crate) subclasses: &'repository [Identity],
    pub(crate) importing: &'repository [&'repository str],
}
