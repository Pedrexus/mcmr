use crate::graph::contracts::Visibility;
use std::collections::{BTreeMap, BTreeSet};

pub(super) struct ReachIndexes<'a> {
    pub(super) modules: BTreeMap<&'a str, &'a str>,
    pub(super) packages: BTreeMap<&'a str, &'a str>,
    pub(super) visibility: BTreeMap<&'a str, Visibility>,
    pub(super) qualnames: BTreeMap<&'a str, &'a str>,
    pub(super) identities: BTreeMap<&'a str, &'a str>,
    pub(super) unresolved_names: BTreeMap<String, usize>,
    pub(super) inheritance_owners: BTreeSet<&'a str>,
}
