use super::construction::workspace;
use super::contracts::{
    EdgeKind, Export, Graph, Language, NodeKind, Reference, Stated, Visibility,
};
use super::naming::Naming;
use super::python::python;
use super::resolution_engine::{ResolutionContext, resolve};
use crate::discovery::Document;
use crate::source::Source;
use rayon::prelude::*;
use std::collections::{BTreeMap, BTreeSet};

mod exports;

/// Build the whole repository graph from documents that were already read.
///
/// One naming pass decides what every file calls itself, one frontend pass per language states the
/// definitions and the references each file makes, and one resolution pass attaches every reference
/// to the declaration it named. A language reaches the graph by adding a frontend to the middle
/// pass, which is why the ends of this function say nothing about any particular language.
pub fn build(root: &str, documents: &[Document]) -> Result<Graph, String> {
    let naming = Naming::of(root, documents);
    let specifiers = crate::typescript::Specifiers::of(root, naming.typescript(documents))?;
    let (mut nodes, mut edges) = workspace(root, documents, &naming);
    let mut references: Vec<Reference> = Vec::new();
    let mut export_references: Vec<Reference> = Vec::new();
    let mut frontends: Vec<(usize, String, Stated)> = documents
        .par_iter()
        .enumerate()
        .filter_map(|(index, document)| {
            let (language, module) = naming.module(&document.relative)?;
            let source = Source::new(document);
            let stated = match language {
                Language::Python => python(source, &module),
                Language::Rust => crate::rust::graph(source, &module),
                Language::TypeScript => crate::typescript::graph(source, &module, &specifiers),
                native => crate::native::graph(source, &module, native),
            }?;
            Some((index, module, stated))
        })
        .collect();
    frontends.sort_by_key(|(index, _, _)| *index);
    let mut aliases: BTreeMap<String, BTreeMap<String, String>> = BTreeMap::new();
    let mut exports = Vec::new();
    for (index, module, mut stated) in frontends {
        let path = documents[index].relative.clone();
        exports.extend(stated.exports.iter().map(|name| {
            let public_name = format!("{module}.{name}");
            Export {
                module: module.clone(),
                name: name.clone(),
                target: stated.aliases.get(name).cloned().unwrap_or(public_name),
                path: path.clone(),
                nodes: stated.export_nodes.get(name).cloned().unwrap_or_default(),
                consumer_count: 0,
                bypasses: Vec::new(),
            }
        }));
        aliases.insert(module, stated.aliases);
        for node in stated.nodes {
            match nodes.entry(node.id.clone()) {
                std::collections::btree_map::Entry::Vacant(entry) => {
                    entry.insert(node);
                }
                std::collections::btree_map::Entry::Occupied(mut entry) => {
                    let current = entry.get().visibility;
                    entry.get_mut().visibility = narrower(current, node.visibility);
                }
            }
        }
        edges.append(&mut stated.edges);
        references.append(&mut stated.references);
        export_references.append(&mut stated.export_references);
    }
    let symbols: BTreeSet<String> = nodes
        .values()
        .filter(|node| !node.kind.is_path_entity() && node.kind != NodeKind::Parameter)
        .map(|node| node.qualname.clone())
        .collect();
    let modules: BTreeSet<String> = nodes
        .values()
        .filter(|node| node.kind == NodeKind::Module)
        .map(|node| node.qualname.clone())
        .collect();
    exports::enrich(&mut exports, &references, &export_references, &modules);
    let lookup = crate::native::Lookup::of(&symbols);
    for reference in references {
        let reachable = if reference.kind == EdgeKind::Import {
            &modules
        } else {
            &symbols
        };
        match reference.language {
            Language::Rust => {
                crate::rust::resolve(
                    &reference,
                    ResolutionContext {
                        symbols: reachable,
                        aliases: &aliases,
                        nodes: &mut nodes,
                        edges: &mut edges,
                    },
                );
            }
            Language::C | Language::Cpp | Language::Cuda => {
                crate::native::resolve(&reference, reachable, &lookup, &mut nodes, &mut edges);
            }
            Language::TypeScript => {
                crate::typescript::resolve(
                    &reference,
                    crate::typescript::ResolutionContext {
                        modules: &modules,
                        symbols: &symbols,
                        aliases: &aliases,
                        nodes: &mut nodes,
                        edges: &mut edges,
                    },
                );
            }
            _ => resolve(
                &reference,
                ResolutionContext {
                    symbols: reachable,
                    aliases: &aliases,
                    nodes: &mut nodes,
                    edges: &mut edges,
                },
            ),
        }
    }
    Ok(Graph {
        nodes: nodes.into_values().collect(),
        edges,
        exports,
    })
}

fn narrower(left: Visibility, right: Visibility) -> Visibility {
    let rank = |visibility| match visibility {
        Visibility::Private => 0,
        Visibility::Internal => 1,
        Visibility::Protected => 2,
        Visibility::Public => 3,
    };
    if rank(left) <= rank(right) {
        left
    } else {
        right
    }
}
