use super::crate_root::CrateRoot;
use std::collections::BTreeSet;

#[derive(Debug, Default)]
pub struct Crates {
    pub(crate) roots: BTreeSet<CrateRoot>,
}
