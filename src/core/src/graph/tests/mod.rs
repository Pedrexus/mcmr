mod imports;

use super::*;
use crate::discovery::Document;
use std::collections::BTreeSet;

fn graph_of(source: &str) -> Graph {
    build(
        "repo",
        &[
            Document {
                relative: "pkg/__init__.py".to_string(),
                source: String::new(),
            },
            Document {
                relative: "pkg/example.py".to_string(),
                source: source.to_string(),
            },
        ],
    )
    .expect("the graph builds")
}

fn count(graph: &Graph, kind: NodeKind) -> usize {
    graph.nodes.iter().filter(|node| node.kind == kind).count()
}

fn relations(graph: &Graph, kind: EdgeKind) -> usize {
    graph.edges.iter().filter(|edge| edge.kind == kind).count()
}

#[test]
fn the_workspace_holds_the_repository_its_directories_and_its_files() {
    let graph = graph_of("value = 1\n");

    assert_eq!(count(&graph, NodeKind::Repository), 1);
    assert_eq!(count(&graph, NodeKind::Directory), 1);
    assert_eq!(count(&graph, NodeKind::File), 2);
    assert_eq!(count(&graph, NodeKind::Module), 2);
    assert_eq!(count(&graph, NodeKind::Variable), 1);
}

#[test]
fn a_class_carries_its_members_its_bases_and_its_parameters() {
    let graph = graph_of(
        "class Base:\n    pass\n\n\nclass Engine(Base):\n    limit: int = 3\n\n    def run(self, count):\n        self.total = count\n\n    @property\n    def size(self):\n        return 1\n",
    );

    assert_eq!(count(&graph, NodeKind::Class), 2);
    assert_eq!(count(&graph, NodeKind::Method), 1);
    assert_eq!(count(&graph, NodeKind::Property), 1);
    assert_eq!(count(&graph, NodeKind::Attribute), 2);
    assert_eq!(count(&graph, NodeKind::Parameter), 3);
    assert_eq!(relations(&graph, EdgeKind::Inherit), 1);
    assert!(
        graph
            .nodes
            .iter()
            .any(|node| node.id == "python:method:pkg.example.Engine.run")
    );
}

#[test]
fn enum_variants_are_not_reachable_data_fields() {
    let graph = graph_of(
        "from enum import StrEnum\n\n\nclass Color(StrEnum):\n    RED = 'red'\n    BLUE = 'blue'\n",
    );
    let declarations = reach(&graph)
        .into_iter()
        .flat_map(|summary| summary.declarations)
        .collect::<Vec<_>>();

    assert!(
        declarations
            .iter()
            .all(|declaration| !declaration.qualname.contains("Color.RED")
                && !declaration.qualname.contains("Color.BLUE"))
    );
}

#[test]
fn every_frontend_marks_enumerations_and_hides_their_variants_from_state() {
    let graph = build(
        "repo",
        &[
            Document {
                relative: "src/color.rs".to_string(),
                source: "enum RustColor { Red, Blue }\n".to_string(),
            },
            Document {
                relative: "src/color.ts".to_string(),
                source: "enum TypeScriptColor { Red, Blue }\n".to_string(),
            },
            Document {
                relative: "src/color.cpp".to_string(),
                source: "enum NativeColor { Red, Blue };\n".to_string(),
            },
        ],
    )
    .expect("the multilingual graph builds");
    let enums = graph
        .nodes
        .iter()
        .filter(|node| node.kind == NodeKind::Class && node.is_enum)
        .map(|node| node.qualname.rsplit([':', '.']).next().unwrap_or_default())
        .collect::<BTreeSet<_>>();
    let declarations = reach(&graph)
        .into_iter()
        .flat_map(|summary| summary.declarations)
        .collect::<Vec<_>>();

    assert_eq!(
        enums,
        BTreeSet::from(["NativeColor", "RustColor", "TypeScriptColor"])
    );
    assert!(declarations.iter().all(|declaration| {
        !["Red", "Blue"]
            .iter()
            .any(|variant| declaration.qualname.ends_with(variant))
    }));
}

#[test]
fn a_call_resolves_to_a_definition_and_a_constructor_becomes_an_instantiation() {
    let graph = graph_of(
        "class Engine:\n    pass\n\n\ndef build():\n    return Engine()\n\n\ndef start():\n    return build()\n",
    );

    assert_eq!(relations(&graph, EdgeKind::Instantiate), 1);
    assert_eq!(relations(&graph, EdgeKind::Call), 1);
}

#[test]
fn a_first_class_name_and_a_type_alias_reach_the_declarations_they_name() {
    let graph = graph_of(
        "class Answer:\n    pass\n\n\ndef promised(value):\n    return value\n\n\ndef run(values):\n    mapped = map(promised, values)\n    alias = Answer | None\n    return mapped, alias\n",
    );
    let summaries = reach(&graph);
    let module = summaries
        .iter()
        .find(|item| item.path == "pkg/example.py")
        .unwrap();
    let promised = module
        .declarations
        .iter()
        .find(|item| item.qualname == "pkg.example.promised")
        .unwrap();
    let answer = module
        .declarations
        .iter()
        .find(|item| item.qualname == "pkg.example.Answer")
        .unwrap();

    assert_eq!(promised.references.own_file_references, 1);
    assert_eq!(answer.references.own_file_references, 1);
}

#[test]
fn a_call_to_an_inherited_class_method_still_reaches_the_receiver_class() {
    let graph = graph_of(
        "class Payload:\n    pass\n\n\ndef parse():\n    return Payload.model_validate_json('{}')\n",
    );
    let payload = reach(&graph)
        .into_iter()
        .flat_map(|summary| summary.declarations)
        .find(|declaration| declaration.qualname == "pkg.example.Payload")
        .unwrap();

    assert_eq!(payload.references.own_file_references, 1);
}

#[test]
fn a_public_rust_item_inside_a_private_module_is_not_a_public_surface() {
    let mut module = node(Language::Rust, NodeKind::Module, "core::private");
    module.visibility = Visibility::Private;
    module.path = Some("src/lib.rs".to_string());
    let mut function = node(Language::Rust, NodeKind::Function, "core::private::helper");
    function.path = Some("src/lib.rs".to_string());
    function.line = Some(2);
    let graph = Graph {
        nodes: vec![module, function],
        edges: Vec::new(),
        exports: Vec::new(),
    };
    let helper = reach(&graph)
        .into_iter()
        .flat_map(|summary| summary.declarations)
        .find(|declaration| declaration.qualname == "core::private::helper")
        .expect("the nested function contributes reach evidence");

    assert_eq!(helper.visibility, Visibility::Internal);
}

#[test]
fn a_private_rust_module_keeps_its_visibility_when_its_file_is_joined() {
    let graph = build(
        "repo",
        &[
            Document {
                relative: "kernel/src/lib.rs".to_string(),
                source: "mod walk;\n".to_string(),
            },
            Document {
                relative: "kernel/src/walk.rs".to_string(),
                source: "pub fn bounds() {}\n".to_string(),
            },
        ],
    )
    .expect("the Rust module graph builds");
    let bounds = reach(&graph)
        .into_iter()
        .flat_map(|summary| summary.declarations)
        .find(|declaration| declaration.qualname.ends_with("::walk::bounds"))
        .expect("the public helper contributes reach evidence");

    assert_eq!(bounds.visibility, Visibility::Internal);
}

#[test]
fn component_registration_reaches_every_concrete_subclass() {
    let graph =
        graph_of("class Source(Component):\n    pass\n\n\nclass Concrete(Source):\n    pass\n");
    let concrete = reach(&graph)
        .into_iter()
        .flat_map(|summary| summary.declarations)
        .find(|declaration| declaration.qualname == "pkg.example.Concrete")
        .expect("the component subclass contributes reach evidence");

    assert!(concrete.is_decorated);
}

#[test]
fn a_stub_declaration_is_a_published_binding_surface() {
    let graph = build(
        "repo",
        &[Document {
            relative: "pkg/kernel.pyi".to_string(),
            source: "class Tables:\n    pass\n\n\ndef open_tables() -> Tables: ...\n".to_string(),
        }],
    )
    .expect("the Python stub graph builds");
    let declarations: Vec<Declaration> = reach(&graph)
        .into_iter()
        .flat_map(|summary| summary.declarations)
        .collect();

    assert!(
        declarations
            .iter()
            .all(|declaration| declaration.is_decorated)
    );
}

#[test]
fn a_python_type_parameter_reaches_its_bound_and_default() {
    let graph = graph_of(
        "class Bound:\n    pass\n\n\nclass Default:\n    pass\n\n\ntype Choice[T: Bound = Default] = list[T]\n",
    );
    let summaries = reach(&graph);
    let module = summaries
        .iter()
        .find(|item| item.path == "pkg/example.py")
        .unwrap();

    for name in ["pkg.example.Bound", "pkg.example.Default"] {
        let declaration = module
            .declarations
            .iter()
            .find(|item| item.qualname == name)
            .unwrap();
        assert_eq!(declaration.references.own_file_references, 1);
    }
}

#[test]
fn an_unresolved_call_stays_visible_rather_than_being_dropped() {
    let graph = graph_of("def run(handler):\n    return handler()\n");

    assert_eq!(count(&graph, NodeKind::UnresolvedSymbol), 1);
    assert!(
        graph
            .nodes
            .iter()
            .any(|node| node.qualname == "pkg.example::handler")
    );
    assert!(
        graph
            .edges
            .iter()
            .any(|edge| edge.resolution == Resolution::Unresolved)
    );
}

#[test]
fn a_type_checking_branch_contributes_no_runtime_structure() {
    let graph = graph_of(
        "from typing import TYPE_CHECKING\n\nif TYPE_CHECKING:\n    from other import Thing\nelse:\n    Thing = None\n",
    );
    let imports: Vec<&Edge> = graph
        .edges
        .iter()
        .filter(|edge| edge.kind == EdgeKind::Import)
        .collect();

    assert_eq!(imports.len(), 1);
    assert!(imports[0].target.contains("typing"));
}

#[test]
fn an_import_of_a_reexported_symbol_reaches_what_defines_it() {
    let graph = build(
        "repo",
        &[
            Document {
                relative: "pkg/__init__.py".to_string(),
                source: "from .decorators import rule\n".to_string(),
            },
            Document {
                relative: "pkg/decorators.py".to_string(),
                source: "def rule():\n    pass\n".to_string(),
            },
            Document {
                relative: "pkg/api.py".to_string(),
                source: "from pkg import rule\n".to_string(),
            },
        ],
    )
    .expect("the graph builds");
    let reached: Vec<&str> = graph
        .edges
        .iter()
        .filter(|edge| edge.kind == EdgeKind::Import && edge.path == "pkg/api.py")
        .map(|edge| edge.target.as_str())
        .collect();

    assert_eq!(reached, vec!["python:module:pkg.decorators"]);
}
