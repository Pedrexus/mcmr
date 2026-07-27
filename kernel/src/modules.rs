use crate::graph::{EdgeKind, Graph, Node, NodeKind};
use serde_json::{Value, json};
use std::collections::{BTreeMap, BTreeSet};

/// Every module a repository declares, and every import arrow running between two of them.
///
/// The coupling family and the dependency family are two projections of this one index, so both
/// spell a module the way the graph does and neither can drift from the other. That mattered
/// enough to be worth a shared type. An edge list whose sources are file paths and whose targets
/// are package names is a graph with no path through it at all, and a rule computing components
/// over one can only ever answer zero while reading exactly like a clean repository.
pub struct ModuleImports<'a> {
    declared: BTreeMap<&'a str, &'a Node>,
    arrows: BTreeMap<(&'a str, &'a str), BTreeSet<usize>>,
    outward: BTreeMap<&'a str, BTreeSet<&'a str>>,
    inward: BTreeMap<&'a str, BTreeSet<&'a str>>,
}

impl<'a> ModuleImports<'a> {
    /// Index one built graph into the modules files declare and the imports relating them.
    ///
    /// A module here is the one a file declares, which is the unit both this kernel and the Archy
    /// oracle name. A nested Rust `mod` and a C++ namespace are module nodes too, so an import
    /// either of them states is folded onto the file that holds it rather than counted as an
    /// arrow between two halves of one source file. An import of a package this repository does
    /// not own is dropped, since a row nobody here can edit is not part of this architecture.
    pub fn of(graph: &'a Graph) -> Self {
        let files: BTreeSet<&str> = graph
            .edges
            .iter()
            .filter(|edge| edge.kind == EdgeKind::Define && edge.source.starts_with("path:file:"))
            .map(|edge| edge.target.as_str())
            .collect();
        let mut declared: BTreeMap<&str, &Node> = BTreeMap::new();
        let mut holder: BTreeMap<&str, &str> = BTreeMap::new();
        for node in &graph.nodes {
            let Some(path) = node.path.as_deref() else {
                continue;
            };
            if node.kind == NodeKind::Module {
                holder.insert(node.id.as_str(), path);
                if files.contains(node.id.as_str()) {
                    declared.insert(path, node);
                }
            }
        }
        let mut arrows: BTreeMap<(&str, &str), BTreeSet<usize>> = BTreeMap::new();
        let mut outward: BTreeMap<&str, BTreeSet<&str>> = BTreeMap::new();
        let mut inward: BTreeMap<&str, BTreeSet<&str>> = BTreeMap::new();
        for edge in &graph.edges {
            let (Some(importer), Some(imported)) = (
                holder.get(edge.source.as_str()),
                holder.get(edge.target.as_str()),
            ) else {
                continue;
            };
            if edge.kind != EdgeKind::Import
                || !declared.contains_key(importer)
                || !declared.contains_key(imported)
            {
                continue;
            }
            // A nested Rust module importing its parent changes lexical visibility inside one
            // file. The graph keeps that relation, while the architecture index folds nested
            // modules onto their file and must not turn it into a one-file dependency cycle.
            if importer == imported && edge.source != edge.target {
                continue;
            }
            arrows
                .entry((importer, imported))
                .or_default()
                .insert(edge.line.max(1));
            if importer != imported {
                outward.entry(importer).or_default().insert(imported);
                inward.entry(imported).or_default().insert(importer);
            }
        }
        Self {
            declared,
            arrows,
            outward,
            inward,
        }
    }

    /// Return every module a file of this repository declares, keyed by that file's path.
    pub fn declared(&self) -> &BTreeMap<&'a str, &'a Node> {
        &self.declared
    }

    /// Return the qualified name the graph gives the module one path declares.
    pub fn name(&self, path: &str) -> &'a str {
        self.declared
            .get(path)
            .map(|node| node.qualname.as_str())
            .unwrap_or_default()
    }

    /// Return every import arrow, with the lines that state it, importer path first.
    ///
    /// A module importing itself is kept, since an explicit self import is a cycle of one and the
    /// rule that reads these counts it as such. Coupling drops it instead, because a module cannot
    /// make itself harder to change.
    pub fn arrows(&self) -> impl Iterator<Item = (&'a str, &'a str, &BTreeSet<usize>)> {
        self.arrows
            .iter()
            .map(|((importer, imported), lines)| (*importer, *imported, lines))
    }

    /// Return the modules the one at this path imports, leaving out itself.
    pub fn imports(&self, path: &str) -> Vec<&'a str> {
        Self::side(&self.outward, path)
    }

    /// Return the modules of this repository that import the one at this path, leaving out itself.
    pub fn importers(&self, path: &str) -> Vec<&'a str> {
        Self::side(&self.inward, path)
    }

    /// Return what one side of the import relation holds for a path, in the order paths sort.
    fn side(held: &BTreeMap<&'a str, BTreeSet<&'a str>>, path: &str) -> Vec<&'a str> {
        held.get(path)
            .map(|found| found.iter().copied().collect())
            .unwrap_or_default()
    }
}

/// State the whole module dependency graph as the one fact a repository-wide rule reads.
///
/// One fact rather than one per file, because whether an import runs in a cycle is a question
/// about several modules at once and no file can see the modules importing it. Every edge names
/// both ends the way the graph names them and carries the site that states the import, so a
/// component a rule finds has somewhere to point.
pub fn dependencies(graph: &Graph) -> Value {
    let index = ModuleImports::of(graph);
    let edges: Vec<Value> = index
        .arrows()
        .map(|(importer, imported, lines)| {
            json!({
                "source": index.name(importer),
                "target": index.name(imported),
                "path": importer,
                "line": lines.iter().next().copied().unwrap_or(1),
            })
        })
        .collect();
    json!({
        "key": "dependencies:repository",
        "span": {"path": ""},
        "import_edges": edges,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::discovery::Document;

    fn fact_of(sources: &[(&str, &str)]) -> Value {
        let documents: Vec<Document> = sources
            .iter()
            .map(|(relative, source)| Document {
                relative: (*relative).to_string(),
                source: (*source).to_string(),
            })
            .collect();
        dependencies(&crate::graph::build("repo", &documents))
    }

    fn pairs(fact: &Value) -> Vec<(String, String)> {
        fact["import_edges"]
            .as_array()
            .expect("an edge list")
            .iter()
            .map(|edge| {
                (
                    edge["source"].as_str().unwrap_or_default().to_string(),
                    edge["target"].as_str().unwrap_or_default().to_string(),
                )
            })
            .collect()
    }

    #[test]
    fn both_ends_of_an_edge_are_named_the_way_the_graph_names_a_module() {
        let fact = fact_of(&[
            ("pkg/__init__.py", ""),
            ("pkg/core.py", "from pkg import reader\n"),
            ("pkg/reader.py", "from pkg import core\n"),
        ]);

        assert_eq!(
            pairs(&fact),
            [
                ("pkg.core".to_string(), "pkg.reader".to_string()),
                ("pkg.reader".to_string(), "pkg.core".to_string()),
            ]
        );
    }

    #[test]
    fn one_fact_answers_for_the_whole_repository_rather_than_for_one_file() {
        let fact = fact_of(&[
            ("pkg/__init__.py", ""),
            ("pkg/core.py", "value = 1\n"),
            ("pkg/reader.py", "from pkg import core\n"),
        ]);

        assert_eq!(fact["key"], "dependencies:repository");
        assert_eq!(fact["span"]["path"], "");
        assert_eq!(fact["import_edges"].as_array().map(Vec::len), Some(1));
    }

    #[test]
    fn an_edge_carries_the_file_and_the_first_line_that_states_the_import() {
        let fact = fact_of(&[
            ("pkg/__init__.py", ""),
            ("pkg/core.py", "value = 1\n"),
            (
                "pkg/reader.py",
                "import os\n\nfrom pkg import core\nfrom pkg.core import value\n",
            ),
        ]);
        let edges = fact["import_edges"].as_array().expect("an edge list");

        assert_eq!(edges.len(), 1);
        assert_eq!(edges[0]["path"], "pkg/reader.py");
        assert_eq!(edges[0]["line"], 3);
    }

    #[test]
    fn an_import_of_a_package_this_repository_does_not_own_is_no_edge_at_all() {
        let fact = fact_of(&[
            ("pkg/__init__.py", ""),
            (
                "pkg/core.py",
                "import json\nfrom collections.abc import Iterator\n",
            ),
        ]);

        assert_eq!(pairs(&fact), []);
    }

    #[test]
    fn a_module_importing_itself_states_an_arrow_of_one() {
        let fact = fact_of(&[
            ("pkg/__init__.py", ""),
            ("pkg/core.py", "from pkg import core\n"),
        ]);

        assert_eq!(
            pairs(&fact),
            [("pkg.core".to_string(), "pkg.core".to_string())]
        );
    }

    #[test]
    fn a_nested_rust_module_importing_its_parent_is_not_a_file_cycle() {
        let fact = fact_of(&[(
            "engine/src/core.rs",
            "pub struct Frame;\n\n#[cfg(test)]\nmod tests {\n    use super::*;\n}\n",
        )]);

        assert_eq!(pairs(&fact), []);
    }

    #[test]
    fn a_rust_crate_states_the_same_edges_the_python_frontend_would() {
        let fact = fact_of(&[
            ("engine/src/lib.rs", "pub mod core;\npub mod reader;\n"),
            ("engine/src/core.rs", "pub struct Frame;\n"),
            (
                "engine/src/reader.rs",
                "use crate::core::Frame;\n\npub fn read(frame: Frame) -> Frame {\n    frame\n}\n",
            ),
        ]);

        assert_eq!(
            pairs(&fact),
            [("engine::reader".to_string(), "engine::core".to_string())]
        );
    }

    #[test]
    fn the_index_reports_each_side_of_the_arrow_without_counting_a_self_import() {
        let documents: Vec<Document> = [
            ("pkg/__init__.py", ""),
            ("pkg/core.py", "from pkg import core\n"),
            ("pkg/reader.py", "from pkg import core\n"),
        ]
        .iter()
        .map(|(relative, source)| Document {
            relative: (*relative).to_string(),
            source: (*source).to_string(),
        })
        .collect();
        let graph = crate::graph::build("repo", &documents);
        let index = ModuleImports::of(&graph);

        assert_eq!(index.importers("pkg/core.py"), ["pkg/reader.py"]);
        assert_eq!(index.imports("pkg/core.py"), Vec::<&str>::new());
        assert_eq!(index.imports("pkg/reader.py"), ["pkg/core.py"]);
        assert_eq!(index.name("pkg/core.py"), "pkg.core");
        assert_eq!(index.declared().len(), 3);
    }
}
