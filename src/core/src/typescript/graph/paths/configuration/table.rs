use super::mapping::Mapping;

/// The alias mappings one configuration file states, and the directory those mappings govern.
#[derive(Debug)]
pub(super) struct Table {
    pub(super) directory: String,
    pub(super) mappings: Vec<Mapping>,
}
