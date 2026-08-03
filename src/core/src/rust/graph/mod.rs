use crate::graph::Stated;
use crate::source::Source;
use std::collections::{BTreeMap, BTreeSet};

mod callable;
mod callable_identity;
mod collector;

pub(super) use collector::Collector;

/// Build the part of the repository graph one Rust file states.
pub fn graph(source: Source, module: &str) -> Option<Stated> {
    let file = syn::parse_file(&source.text).ok()?;
    let mut collector = Collector::new(source, module.to_string());
    collector.items(&file.items);
    Some(Stated {
        nodes: collector.nodes,
        edges: collector.edges,
        references: collector.references,
        export_references: Vec::new(),
        aliases: collector.aliases,
        exports: BTreeSet::new(),
        export_nodes: BTreeMap::new(),
    })
}
