use std::collections::BTreeSet;

pub(super) struct ScopeBindings<'a> {
    pub(super) inherited: &'a BTreeSet<String>,
    pub(super) visible: &'a BTreeSet<String>,
}
