use super::entry::NestedEntry;

pub(crate) struct NestedLocation<'a> {
    pub(crate) parent_id: &'a str,
    pub(crate) container_ordinal: u64,
    pub(crate) map_key: Option<String>,
}

impl<'a> NestedLocation<'a> {
    pub(crate) fn from_entry(entry: NestedEntry<'a>) -> Self {
        Self {
            parent_id: entry.container_id,
            container_ordinal: entry.ordinal,
            map_key: entry.map_key,
        }
    }
}
