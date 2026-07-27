use crate::graph::{Graph, Language, Node, NodeKind};
use crate::modules::ModuleImports;
use serde::Serialize;
use serde_json::{Value, json};
use std::collections::BTreeMap;

/// What one module depends on and what depends on it, beside how much of it is a contract.
///
/// These four counts are the whole input to Robert Martin's package metrics, and they arrive
/// together because none of them means anything alone. Being depended on is only a burden when the
/// module is concrete, and being abstract is only useful when something depends on it.
#[derive(Clone, Debug, Default, Serialize)]
pub struct Coupling {
    pub module: String,
    pub afferent_count: usize,
    pub efferent_count: usize,
}

/// Summarize every module the repository declares, with the coupling of everything it imports.
///
/// One fact per module rather than one for the repository, because every question a layering
/// contract answers is a question about one module and the arrows leaving it. Carrying the
/// coupling of each imported module inside the importer's own fact is what lets a rule compare two
/// stabilities without a second lookup, which is the whole of the Stable Dependencies Principle.
pub fn modules(graph: &Graph) -> Vec<Value> {
    Modules::of(graph).facts()
}

/// The import arrows of the repository, beside the types each module declares.
///
/// Which module imports which is the shared index rather than a second reading of the graph, so
/// the coupling counts and the dependency edge list can never disagree about what a module is
/// called. Only abstractness is this family's own question, and a type is the only declaration
/// that can answer it.
struct Modules<'a> {
    imports: ModuleImports<'a>,
    types: BTreeMap<&'a str, Vec<&'a Node>>,
}

impl<'a> Modules<'a> {
    /// Index one built graph into the module import relation and the types each module holds.
    fn of(graph: &'a Graph) -> Self {
        let mut types: BTreeMap<&str, Vec<&Node>> = BTreeMap::new();
        for node in &graph.nodes {
            if node.kind == NodeKind::Class
                && let Some(path) = node.path.as_deref()
            {
                types.entry(path).or_default().push(node);
            }
        }
        Self {
            imports: ModuleImports::of(graph),
            types,
        }
    }

    /// Return one fact for every module a file of this repository declares.
    fn facts(&self) -> Vec<Value> {
        self.imports
            .declared()
            .iter()
            .map(|(path, node)| self.fact(path, node))
            .collect()
    }

    /// State one module as the fact a rule reads, with nothing decided for it.
    fn fact(&self, path: &str, module: &Node) -> Value {
        let held = self.types.get(path).map(Vec::as_slice).unwrap_or_default();
        json!({
            "key": format!("coupling:{}", module.qualname),
            "span": {"path": path},
            "language": module.language.unwrap_or(Language::Python),
            "module": module.qualname,
            "afferent_count": self.imports.importers(path).len(),
            "efferent_count": self.imports.imports(path).len(),
            "declaration_count": held.len(),
            "abstract_declaration_count": held.iter().filter(|node| node.is_abstract).count(),
            "dependencies": self.dependencies(path),
        })
    }

    /// Return the coupling of every module this one imports, in the order their paths sort.
    ///
    /// An import of a package this repository does not own never reaches here, since Martin's
    /// instability describes how a component sits inside its own architecture and a module
    /// importing twenty external crates has not become unstable by doing so.
    fn dependencies(&self, path: &str) -> Vec<Coupling> {
        self.imports
            .imports(path)
            .into_iter()
            .map(|target| Coupling {
                module: self.imports.name(target).to_string(),
                afferent_count: self.imports.importers(target).len(),
                efferent_count: self.imports.imports(target).len(),
            })
            .collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::discovery::Document;

    fn facts_of(sources: &[(&str, &str)]) -> Vec<Value> {
        let documents: Vec<Document> = sources
            .iter()
            .map(|(relative, source)| Document {
                relative: (*relative).to_string(),
                source: (*source).to_string(),
            })
            .collect();
        modules(&crate::graph::build("repo", &documents))
    }

    fn module<'a>(facts: &'a [Value], name: &str) -> &'a Value {
        facts
            .iter()
            .find(|fact| fact["module"] == name)
            .expect("the module is in the graph")
    }

    fn dependency<'a>(fact: &'a Value, name: &str) -> &'a Value {
        fact["dependencies"]
            .as_array()
            .expect("a dependency list")
            .iter()
            .find(|item| item["module"] == name)
            .expect("the dependency is stated")
    }

    #[test]
    fn coupling_counts_the_modules_on_each_side_of_the_import_arrow() {
        let facts = facts_of(&[
            ("pkg/__init__.py", ""),
            ("pkg/core.py", "value = 1\n"),
            ("pkg/reader.py", "from pkg import core\n"),
            (
                "pkg/writer.py",
                "from pkg import core\nfrom pkg import reader\n",
            ),
        ]);

        assert_eq!(module(&facts, "pkg.core")["afferent_count"], 2);
        assert_eq!(module(&facts, "pkg.core")["efferent_count"], 0);
        assert_eq!(module(&facts, "pkg.reader")["afferent_count"], 1);
        assert_eq!(module(&facts, "pkg.reader")["efferent_count"], 1);
        assert_eq!(module(&facts, "pkg.writer")["afferent_count"], 0);
        assert_eq!(module(&facts, "pkg.writer")["efferent_count"], 2);
    }

    #[test]
    fn an_importer_carries_the_coupling_of_everything_it_imports() {
        let facts = facts_of(&[
            ("pkg/__init__.py", ""),
            ("pkg/core.py", "value = 1\n"),
            ("pkg/reader.py", "from pkg import core\n"),
            ("pkg/writer.py", "from pkg import core\n"),
        ]);
        let stated = dependency(module(&facts, "pkg.reader"), "pkg.core");

        assert_eq!(stated["afferent_count"], 2);
        assert_eq!(stated["efferent_count"], 0);
    }

    #[test]
    fn an_external_package_is_left_out_of_both_counts() {
        let facts = facts_of(&[
            ("pkg/__init__.py", ""),
            ("pkg/core.py", "import json\nimport os\nimport re\n"),
        ]);

        assert_eq!(module(&facts, "pkg.core")["efferent_count"], 0);
        assert!(
            module(&facts, "pkg.core")["dependencies"]
                .as_array()
                .expect("a dependency list")
                .is_empty()
        );
    }

    #[test]
    fn two_files_importing_the_same_module_twice_still_count_it_once() {
        let facts = facts_of(&[
            ("pkg/__init__.py", ""),
            ("pkg/core.py", "value = 1\n"),
            (
                "pkg/reader.py",
                "from pkg import core\nfrom pkg.core import value\n",
            ),
        ]);

        assert_eq!(module(&facts, "pkg.reader")["efferent_count"], 1);
        assert_eq!(module(&facts, "pkg.core")["afferent_count"], 1);
    }

    #[test]
    fn a_python_contract_is_an_abstract_base_a_protocol_or_a_required_member() {
        let facts = facts_of(&[
            ("pkg/__init__.py", ""),
            (
                "pkg/shapes.py",
                "from abc import ABC, abstractmethod\nfrom typing import Protocol\n\n\nclass Shape(ABC):\n    pass\n\n\nclass Reader(Protocol):\n    def read(self) -> str: ...\n\n\nclass Sized:\n    @abstractmethod\n    def size(self) -> int: ...\n\n\nclass Circle(Shape):\n    def area(self) -> float:\n        return 1.0\n",
            ),
        ]);

        assert_eq!(module(&facts, "pkg.shapes")["declaration_count"], 4);
        assert_eq!(
            module(&facts, "pkg.shapes")["abstract_declaration_count"],
            3
        );
    }

    #[test]
    fn a_metaclass_keyword_states_the_same_contract_a_base_class_does() {
        let facts = facts_of(&[
            ("pkg/__init__.py", ""),
            (
                "pkg/meta.py",
                "import abc\n\n\nclass Shape(metaclass=abc.ABCMeta):\n    pass\n",
            ),
        ]);

        assert_eq!(module(&facts, "pkg.meta")["abstract_declaration_count"], 1);
    }

    #[test]
    fn a_rust_trait_is_the_contract_and_every_other_named_type_is_not() {
        let facts = facts_of(&[(
            "engine/src/lib.rs",
            "pub trait Codec {\n    fn encode(&self) -> String;\n}\n\npub struct Frame {\n    pub width: usize,\n}\n\npub enum Mode {\n    Fast,\n}\n",
        )]);

        assert_eq!(module(&facts, "engine")["declaration_count"], 3);
        assert_eq!(module(&facts, "engine")["abstract_declaration_count"], 1);
    }

    #[test]
    fn a_native_contract_is_the_type_that_declares_a_pure_virtual() {
        let facts = facts_of(&[(
            "src/shape.hpp",
            "class Shape {\n public:\n  virtual double area() const = 0;\n  virtual Shape* clone() = 0;\n};\n\nclass Circle : public Shape {\n public:\n  double area() const { return 1.0; }\n};\n\nclass Counter {\n public:\n  int limit = 0;\n};\n",
        )]);

        assert_eq!(module(&facts, "src::shape")["declaration_count"], 3);
        assert_eq!(
            module(&facts, "src::shape")["abstract_declaration_count"],
            1
        );
    }

    #[test]
    fn a_nested_module_imports_on_behalf_of_the_file_that_holds_it() {
        let facts = facts_of(&[
            ("engine/src/lib.rs", "pub mod core;\npub mod reader;\n"),
            ("engine/src/core.rs", "pub struct Frame;\n"),
            (
                "engine/src/reader.rs",
                "mod inner {\n    use crate::core::Frame;\n\n    pub fn read(frame: Frame) -> Frame {\n        frame\n    }\n}\n",
            ),
        ]);

        assert_eq!(module(&facts, "engine::reader")["efferent_count"], 1);
        assert_eq!(module(&facts, "engine::core")["afferent_count"], 1);
        assert!(
            facts
                .iter()
                .all(|fact| fact["module"] != "engine::reader::inner")
        );
    }

    #[test]
    fn a_module_alone_in_a_repository_states_zero_on_both_sides() {
        let facts = facts_of(&[("alone.py", "value = 1\n")]);

        assert_eq!(facts.len(), 1);
        assert_eq!(facts[0]["afferent_count"], 0);
        assert_eq!(facts[0]["efferent_count"], 0);
        assert_eq!(facts[0]["declaration_count"], 0);
        assert_eq!(facts[0]["key"], "coupling:alone");
        assert_eq!(facts[0]["span"]["path"], "alone.py");
    }

    #[test]
    fn a_module_importing_itself_is_never_its_own_dependency() {
        let facts = facts_of(&[
            ("pkg/__init__.py", ""),
            ("pkg/core.py", "from pkg import core\n"),
        ]);

        assert_eq!(module(&facts, "pkg.core")["efferent_count"], 0);
        assert_eq!(module(&facts, "pkg.core")["afferent_count"], 0);
    }
}
