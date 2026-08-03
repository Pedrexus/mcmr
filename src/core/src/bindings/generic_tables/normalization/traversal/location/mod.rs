use super::nested::NestedEntry;

pub(crate) struct ValueLocation<'a> {
    pub(crate) parent_id: &'a str,
    pub(crate) container_id: String,
    pub(crate) container_ordinal: Option<u64>,
    pub(crate) container_length: u64,
    pub(crate) value_id: String,
    pub(crate) ordinal: u64,
    pub(crate) map_key: Option<String>,
}

impl<'a> ValueLocation<'a> {
    pub(crate) fn nested(entry: NestedEntry<'a>) -> Self {
        Self {
            parent_id: entry.container_id,
            container_id: entry.container_id.to_string(),
            container_ordinal: Some(entry.container_ordinal),
            container_length: entry.container_length,
            value_id: format!("{}:{}", entry.container_id, entry.ordinal),
            ordinal: entry.ordinal,
            map_key: entry.map_key,
        }
    }

    pub(crate) fn top(
        parent_id: &'a str,
        ordinal: u64,
        relation: &str,
        length: usize,
        map_key: Option<String>,
    ) -> Self {
        let container_id = format!("{parent_id}/{relation}");
        Self {
            parent_id,
            value_id: format!("{container_id}:{ordinal}"),
            container_id,
            container_ordinal: None,
            container_length: length as u64,
            ordinal,
            map_key,
        }
    }
}
