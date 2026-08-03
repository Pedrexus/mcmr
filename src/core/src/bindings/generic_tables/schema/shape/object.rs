use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone, Debug)]
pub(crate) struct ObjectSchema<Schema> {
    pub(crate) fields: BTreeMap<String, Schema>,
    pub(crate) required: BTreeSet<String>,
}
