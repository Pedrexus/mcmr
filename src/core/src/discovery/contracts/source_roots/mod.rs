use std::collections::BTreeSet;

#[derive(Debug, Default)]
pub struct SourceRoots {
    pub(crate) directories: BTreeSet<String>,
}
