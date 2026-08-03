use crate::classes::model::Identity;
use std::collections::{BTreeMap, BTreeSet};

pub(super) struct RepositoryRelations<'repository> {
    pub(super) built: BTreeSet<Identity>,
    pub(super) reexported: BTreeSet<Identity>,
    pub(super) reexported_names: BTreeSet<&'repository str>,
    pub(super) directly_exported: BTreeSet<Identity>,
    pub(super) dispatched: BTreeSet<(&'repository str, &'repository str)>,
    pub(super) coimports:
        BTreeMap<&'repository str, Vec<(&'repository str, Vec<&'repository str>)>>,
    pub(super) model_packages: BTreeSet<String>,
}
