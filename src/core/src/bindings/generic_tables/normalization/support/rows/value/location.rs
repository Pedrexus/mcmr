mod container;

pub(crate) use container::ValueContainer;

pub(crate) struct ValueLocation {
    pub(crate) relation: String,
    pub(crate) parent_id: String,
    pub(crate) container: ValueContainer,
    pub(crate) entry_kind: String,
    pub(crate) value_id: String,
    pub(crate) ordinal: u64,
    pub(crate) map_key: Option<String>,
}
