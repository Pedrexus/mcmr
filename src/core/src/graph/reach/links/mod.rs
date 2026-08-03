use std::collections::BTreeMap;

pub(super) struct ReachLinks<'a> {
    pub(super) owners: BTreeMap<&'a str, &'a str>,
    pub(super) by_qualname: BTreeMap<&'a str, &'a str>,
}
