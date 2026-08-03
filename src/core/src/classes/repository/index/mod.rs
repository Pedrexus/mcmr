use crate::classes::model::{Declared, Identity, Stated};
use std::collections::{BTreeMap, BTreeSet};

pub(super) struct RepositoryIndex<'repository> {
    pub(super) definitions: BTreeMap<Identity, &'repository Declared>,
    pub(super) modules: BTreeMap<&'repository str, &'repository Stated>,
    pub(super) paths: BTreeMap<&'repository str, &'repository str>,
    pub(super) owners: BTreeMap<&'repository str, &'repository str>,
    pub(super) bases: BTreeMap<Identity, Vec<Identity>>,
    pub(super) subclasses: BTreeMap<Identity, Vec<Identity>>,
    pub(super) importers: BTreeMap<Identity, BTreeSet<&'repository str>>,
}
