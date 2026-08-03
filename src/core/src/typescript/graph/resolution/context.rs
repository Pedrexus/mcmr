use crate::graph::{Edge, Node};
use std::collections::{BTreeMap, BTreeSet};

pub struct ResolutionContext<'graph> {
    pub modules: &'graph BTreeSet<String>,
    pub symbols: &'graph BTreeSet<String>,
    pub aliases: &'graph BTreeMap<String, BTreeMap<String, String>>,
    pub nodes: &'graph mut BTreeMap<String, Node>,
    pub edges: &'graph mut Vec<Edge>,
}
