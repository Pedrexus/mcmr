use crate::bindings::generic_tables::schema::Schema;
use serde_json::Value;

#[derive(Clone, Copy)]
pub(crate) struct EntryContext<'a> {
    pub(crate) relation: &'a str,
    pub(crate) item: &'a Schema,
    pub(crate) parent_id: &'a str,
    pub(crate) length: usize,
    pub(crate) ordinal: u64,
    pub(crate) map_key: Option<&'a str>,
    pub(crate) value: &'a Value,
}
