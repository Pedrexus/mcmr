use crate::bindings::generic_tables::schema::ScalarKind;

#[derive(Clone, Debug, Eq, Hash, PartialEq)]
pub(crate) struct ScalarKey {
    pub(crate) path: String,
    pub(crate) kind: ScalarKind,
}
