use crate::graph::Node;
use std::collections::{BTreeMap, BTreeSet};

pub(super) type DeclaredModules<'a> = (BTreeMap<&'a str, &'a Node>, BTreeMap<&'a str, &'a str>);

pub(super) type ImportRelations<'a> = (
    BTreeMap<(&'a str, &'a str), BTreeSet<usize>>,
    BTreeMap<&'a str, BTreeSet<&'a str>>,
    BTreeMap<&'a str, BTreeSet<&'a str>>,
);
