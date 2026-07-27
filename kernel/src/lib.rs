//! Discovery, parsing, fact extraction, and the repository graph for My Code, My Rules.
//!
//! The binary is a thin shell over this library. Exposing the modules rather than hiding them in
//! one executable is what lets a benchmark measure a single family in isolation, which is the only
//! way to know which one is worth optimizing.

pub mod classes;
pub mod clones;
pub mod comments;
pub mod coupling;
pub mod discovery;
pub mod exceptions;
pub mod families;
pub mod graph;
pub mod history;
pub mod interop;
pub mod lexical;
pub mod modules;
pub mod native;
pub mod overrides;
pub mod project;
pub mod protocol;
pub mod python;
pub mod routes;
pub mod rust;
pub mod source;
pub mod syntax;
pub mod typescript;
pub mod walk;

use protocol::{Request, Response, Stats, VERSION};
use rayon::prelude::*;
use std::collections::BTreeMap;
use std::time::Instant;

/// The families the repository graph answers, which no frontend is ever asked for.
///
/// Each of these is a statement about several files at once. A file cannot see what imports it,
/// which module overrides its methods, or how far a declaration reaches, so a per-file builder
/// answering any of them can only state what one file happens to hold and a rule reading that
/// answers the same thing forever.
const GRAPH_DERIVED: &[&str] = &[
    "DependencyComponentFact",
    "ModuleCouplingFact",
    "OverrideFact",
    "SymbolReachFact",
];

/// Answer one analysis request, which is everything the binary does.
pub fn run(request: &Request) -> Result<Response, String> {
    let discovery_started = Instant::now();
    // One compiled answer to what this request is about, so the walk, the cross-language scan, the
    // route scan, and the history pass all read the same repository rather than four of them.
    let scope = discovery::Scope::of(&request.exclude, &request.suffixes)?;
    let inventory = discovery::collect(request, &scope)?;
    let documents = &inventory.documents;
    let discovery_nanoseconds = discovery_started.elapsed().as_nanos();
    let extraction_started = Instant::now();
    let mut stats = Stats {
        file_count: documents.len(),
        byte_count: documents.iter().map(|document| document.source.len()).sum(),
        discovery_nanoseconds,
        ..Stats::default()
    };
    // The directory family is the one a frontend cannot fill, since only the walk knows what a
    // folder holds. The single thing it cannot read off the tree is whether the modules inside
    // each declare one thing, which every frontend already answered in `ModuleFact`, so that
    // family is built alongside it and dropped again when the caller never asked for it.
    let wants = |name: &str| request.families.iter().any(|family| family == name);
    let built: Vec<String> = request
        .families
        .iter()
        .cloned()
        .chain((wants("DirectoryFact") && !wants("ModuleFact")).then(|| "ModuleFact".to_string()))
        .collect();
    let mut facts: BTreeMap<String, Vec<serde_json::Value>> = built
        .iter()
        .map(|family| (family.clone(), Vec::new()))
        .collect();
    let per_file: Vec<String> = built
        .iter()
        .filter(|family| !GRAPH_DERIVED.contains(&family.as_str()))
        .cloned()
        .collect();
    let packages = discovery::Packages::of(documents);
    // One file's facts never depend on another's, so the only thing that made this sequential was
    // the shared map it wrote into. Each file fills its own and the maps are merged after, which
    // costs one allocation per file and buys every core the machine has.
    let extracted: Vec<(BTreeMap<String, Vec<serde_json::Value>>, Stats)> = documents
        .par_iter()
        .map(|document| {
            let mut held: BTreeMap<String, Vec<serde_json::Value>> = per_file
                .iter()
                .map(|family| (family.clone(), Vec::new()))
                .collect();
            let mut counted = Stats::default();
            match graph::Language::of(&document.relative) {
                Some(graph::Language::TypeScript) => {
                    typescript::extract(document, &mut held, &mut counted);
                }
                Some(graph::Language::Rust) => rust::extract(document, &mut held, &mut counted),
                // The native frontend states which suffixes its own grammars accept, because the
                // inline implementations a template library keeps its bodies in carry no node
                // identity and are not in the language map.
                _ if native::reads(&document.relative) => {
                    native::extract(document, &mut held, &mut counted);
                }
                _ => python::extract(document, &packages, &mut held, &mut counted),
            }
            (held, counted)
        })
        .collect();
    // Documents arrive sorted and rayon keeps their order through the collect, so the merged
    // streams are identical to what one thread would have produced and two runs agree. Only the
    // timings in `stats` differ between runs, as they did before any of this was parallel.
    for (held, counted) in extracted {
        stats.parse_failure_count += counted.parse_failure_count;
        for (family, mut produced) in held {
            if let Some(stream) = facts.get_mut(&family) {
                stream.append(&mut produced);
            }
        }
    }
    for (family, fact) in project::facts(std::path::Path::new(&request.root), &built) {
        if let Some(stream) = facts.get_mut(&family) {
            stream.push(fact);
        }
    }

    // Where an exception belongs is a question about every module at once, so the family is joined
    // after extraction rather than answered one file at a time.
    if let Some(stream) = facts.get_mut("ExceptionFact") {
        stream.extend(exceptions::facts(documents, &packages));
    }
    // Who subclasses a class, who builds one, and who imports it are questions about every module
    // at once, so the file pass leaves those fields alone and this one joins them afterwards.
    if wants("ClassFact") || wants("FunctionFact") {
        classes::enrich(&mut facts, documents, &packages);
    }
    if wants("DirectoryFact") {
        let modules = facts
            .get("ModuleFact")
            .map(Vec::as_slice)
            .unwrap_or_default();
        let catalogs = discovery::definition_catalogs(modules);
        let roots = discovery::SourceRoots::of(&inventory.directories, &packages);
        let directories = discovery::directories(&inventory.directories, &roots, &catalogs);
        facts.insert("DirectoryFact".to_string(), directories);
        if !wants("ModuleFact") {
            facts.remove("ModuleFact");
        }
    }
    stats.extraction_nanoseconds = extraction_started.elapsed().as_nanos();
    let graph_started = Instant::now();
    let root = std::path::Path::new(&request.root);
    if let Some(stream) = facts.get_mut("InteropFact") {
        stream.extend(interop::facts(&interop::scan(root, &scope)));
    }
    if let Some(stream) = facts.get_mut("CloneGroupFact") {
        stream.extend(clones::scan(documents));
    }
    if let Some(stream) = facts.get_mut("RepositoryHistoryFact") {
        stream.extend(history::read(root, &scope));
    }
    if let Some(stream) = facts.get_mut("RouteFact") {
        stream.extend(routes::facts(&routes::scan(root, &scope)));
    }
    let wants_graph = GRAPH_DERIVED
        .iter()
        .any(|family| facts.contains_key(*family));
    let graph = (request.graph || wants_graph).then(|| graph::build(&request.root, documents));
    if let Some(built) = &graph {
        stats.node_count = built.nodes.len();
        stats.edge_count = built.edges.len();
        if let Some(stream) = facts.get_mut("OverrideFact") {
            stream.extend(overrides::pairs(built));
        }
        if let Some(stream) = facts.get_mut("ModuleCouplingFact") {
            stream.extend(coupling::modules(built));
        }
        if let Some(stream) = facts.get_mut("DependencyComponentFact") {
            stream.push(modules::dependencies(built));
        }
        if let Some(stream) = facts.get_mut("SymbolReachFact") {
            stream.extend(graph::reach(built).into_iter().map(|reach| {
                serde_json::json!({
                    "key": format!("reach:{}", reach.module),
                    "span": {"path": reach.path},
                    "language": reach.language,
                    "is_test_module": reach.is_test_module,
                    "declarations": reach.declarations,
                })
            }));
        }
    }
    stats.graph_nanoseconds = graph_started.elapsed().as_nanos();
    stats.fact_count = facts.values().map(Vec::len).sum();
    Ok(Response {
        version: VERSION,
        facts,
        graph: graph.filter(|_| request.graph),
        stats,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn request(root: &str) -> Request {
        Request {
            root: root.to_string(),
            families: vec!["ModuleFact".to_string(), "FunctionFact".to_string()],
            exclude: vec!["**/__pycache__/**".to_string()],
            suffixes: vec![".py".to_string()],
            graph: false,
        }
    }

    #[test]
    fn parallel_extraction_produces_what_one_thread_would_have() {
        let root = concat!(env!("CARGO_MANIFEST_DIR"), "/../src");

        let first = run(&request(root)).expect("the corpus reads");
        let second = run(&request(root)).expect("the corpus reads");

        assert!(first.stats.fact_count > 0);
        assert_eq!(
            serde_json::to_string(&first.facts).unwrap_or_default(),
            serde_json::to_string(&second.facts).unwrap_or_default(),
            "documents arrive sorted and rayon keeps their order, so two runs must agree"
        );
    }
}
