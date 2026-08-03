pub(crate) struct NestedEntry<'a> {
    pub(crate) container_id: &'a str,
    pub(crate) container_ordinal: u64,
    pub(crate) container_length: u64,
    pub(crate) ordinal: u64,
    pub(crate) map_key: Option<String>,
}
