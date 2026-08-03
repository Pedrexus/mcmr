use crate::graph::{Edge, Language, Node, NodeKind, Reference, identity};
use crate::source::Source;
use std::collections::BTreeMap;

mod declarations;
mod references;

/// Every definition and reference collected from one Rust file.
pub(in crate::rust) struct Collector {
    pub(super) source: Source,
    pub(super) scopes: Vec<String>,
    pub(super) enclosing: Vec<String>,
    pub(super) owners: Vec<String>,
    pub(super) receiver: Option<String>,
    pub(super) nodes: Vec<Node>,
    pub(super) edges: Vec<Edge>,
    pub(super) references: Vec<Reference>,
    pub(super) aliases: BTreeMap<String, String>,
}

impl Collector {
    pub(in crate::rust) fn new(source: Source, module: String) -> Self {
        Self {
            source,
            owners: vec![identity(Language::Rust, NodeKind::Module, &module)],
            scopes: vec![module.clone()],
            enclosing: vec![module.clone()],
            receiver: None,
            nodes: Vec::new(),
            edges: Vec::new(),
            references: Vec::new(),
            aliases: BTreeMap::new(),
        }
    }

    pub(super) fn owner(&self) -> String {
        self.owners
            .last()
            .cloned()
            .expect("the Rust collector must retain its module owner")
    }

    pub(super) fn scope(&self) -> String {
        self.scopes
            .last()
            .cloned()
            .expect("the Rust collector must retain its module scope")
    }
}
