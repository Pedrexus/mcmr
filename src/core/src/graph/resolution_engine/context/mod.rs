use crate::graph::contracts::{Edge, Node};
use std::collections::{BTreeMap, BTreeSet};

pub(crate) struct ResolutionContext<'a> {
    pub(crate) symbols: &'a BTreeSet<String>,
    pub(crate) aliases: &'a BTreeMap<String, BTreeMap<String, String>>,
    pub(crate) nodes: &'a mut BTreeMap<String, Node>,
    pub(crate) edges: &'a mut Vec<Edge>,
}
