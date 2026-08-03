use std::collections::{BTreeMap, BTreeSet};

/// Imported, exported, external, and generic names in one module.
#[derive(Default)]
pub(in crate::typescript::graph::collector) struct NameState {
    pub(in crate::typescript::graph::collector) aliases: BTreeMap<String, String>,
    pub(in crate::typescript::graph::collector) externals: BTreeMap<String, String>,
    pub(in crate::typescript::graph::collector) exported: BTreeSet<String>,
    pub(in crate::typescript::graph::collector) generics: BTreeSet<String>,
}
