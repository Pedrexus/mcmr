use super::*;

#[test]
fn explicit_python_exports_count_only_consumers_of_the_public_route() {
    let graph = build(
        "repo",
        &[
            Document {
                relative: "pkg/__init__.py".to_string(),
                source: "from .client import Client\nfrom .engine import Engine\n\n__all__ = [\"Client\", \"Engine\"]\n"
                    .to_string(),
            },
            Document {
                relative: "pkg/client.py".to_string(),
                source: "class Client:\n    pass\n".to_string(),
            },
            Document {
                relative: "pkg/engine.py".to_string(),
                source: "class Engine:\n    pass\n".to_string(),
            },
            Document {
                relative: "consumer.py".to_string(),
                source: "from pkg import Client\n\nclient = Client()\n".to_string(),
            },
            Document {
                relative: "typed_consumer.py".to_string(),
                source: "from typing import TYPE_CHECKING\n\nif TYPE_CHECKING:\n    from pkg import Client\n"
                    .to_string(),
            },
            Document {
                relative: "internal.py".to_string(),
                source: "from pkg.client import Client\n\nclient = Client()\n".to_string(),
            },
            Document {
                relative: "pkg/internal.py".to_string(),
                source: "from pkg.client import Client\n\nclient = Client()\n".to_string(),
            },
        ],
    )
    .expect("the graph builds");
    let exports: Vec<(&str, &str, usize)> = graph
        .exports
        .iter()
        .map(|export| {
            (
                export.name.as_str(),
                export.target.as_str(),
                export.consumer_count,
            )
        })
        .collect();

    assert_eq!(
        exports,
        [
            ("Client", "pkg.client.Client", 2),
            ("Engine", "pkg.engine.Engine", 0),
        ]
    );
    assert_eq!(
        (
            graph.exports[0].nodes[0].text.as_str(),
            graph.exports[0].nodes[0].kind.as_str(),
            graph.exports[0].nodes[0].span.start_column,
        ),
        ("\"Client\"", "sequence-item", 11)
    );
    let bypass = &graph.exports[0].bypasses[0];
    assert_eq!(
        (
            graph.exports[0].bypasses.len(),
            bypass.path.as_str(),
            bypass.module_node.as_ref().map(|node| node.text.as_str()),
            bypass.replacement_module.as_deref(),
            bypass.binding_count,
            bypass.is_cycle_safe,
        ),
        (1, "internal.py", Some("pkg.client"), Some("pkg"), 1, true)
    );
    assert!(graph.exports[1].bypasses.is_empty());
    assert!(
        serde_json::to_value(&graph)
            .expect("the public graph serializes")
            .get("exports")
            .is_none()
    );
}

#[test]
fn grouped_import_bypasses_retain_the_whole_statement_binding_count() {
    let graph = build(
        "repo",
        &[
            Document {
                relative: "pkg/__init__.py".to_string(),
                source:
                    "from .engine import Client, Engine\n\n__all__ = [\"Client\", \"Engine\"]\n"
                        .to_string(),
            },
            Document {
                relative: "pkg/engine.py".to_string(),
                source: "class Client:\n    pass\n\n\nclass Engine:\n    pass\n".to_string(),
            },
            Document {
                relative: "consumer.py".to_string(),
                source: "from pkg.engine import Client, Engine\n".to_string(),
            },
        ],
    )
    .expect("the graph builds");

    assert_eq!(graph.exports[0].bypasses[0].binding_count, 2);
    assert_eq!(graph.exports[1].bypasses[0].binding_count, 2);
    assert_eq!(
        graph.exports[0].bypasses[0]
            .module_node
            .as_ref()
            .map(|node| node.id.as_str()),
        graph.exports[1].bypasses[0]
            .module_node
            .as_ref()
            .map(|node| node.id.as_str())
    );
}

#[test]
fn a_defining_package_imports_its_own_symbol_without_crossing_a_facade() {
    let graph = build(
        "repo",
        &[
            Document {
                relative: "facade/__init__.py".to_string(),
                source: "from internal.engine import Engine\n\n__all__ = [\"Engine\"]\n"
                    .to_string(),
            },
            Document {
                relative: "internal/__init__.py".to_string(),
                source: String::new(),
            },
            Document {
                relative: "internal/engine.py".to_string(),
                source: "class Engine:\n    pass\n".to_string(),
            },
            Document {
                relative: "internal/helper.py".to_string(),
                source: "from internal.engine import Engine\n".to_string(),
            },
            Document {
                relative: "consumer.py".to_string(),
                source: "from internal.engine import Engine\n".to_string(),
            },
        ],
    )
    .expect("the graph builds");

    assert_eq!(graph.exports[0].bypasses.len(), 1);
    assert_eq!(graph.exports[0].bypasses[0].path, "consumer.py");
}

#[test]
fn a_relative_import_is_not_rewritten_when_its_dots_cannot_reach_the_facade() {
    let graph = build(
        "repo",
        &[
            Document {
                relative: "facade/__init__.py".to_string(),
                source: "from app.internal.engine import Engine\n\n__all__ = [\"Engine\"]\n"
                    .to_string(),
            },
            Document {
                relative: "app/__init__.py".to_string(),
                source: String::new(),
            },
            Document {
                relative: "app/consumer.py".to_string(),
                source: "from .internal.engine import Engine\n".to_string(),
            },
            Document {
                relative: "app/internal/__init__.py".to_string(),
                source: String::new(),
            },
            Document {
                relative: "app/internal/engine.py".to_string(),
                source: "class Engine:\n    pass\n".to_string(),
            },
        ],
    )
    .expect("the graph builds");

    assert_eq!(graph.exports[0].bypasses.len(), 1);
    assert!(graph.exports[0].bypasses[0].replacement_module.is_none());
}

#[test]
fn a_facade_that_reaches_the_consumer_never_offers_an_automatic_rewrite() {
    let graph = build(
        "repo",
        &[
            Document {
                relative: "facade/__init__.py".to_string(),
                source: "from engine import Engine\nfrom consumer import use\n\n__all__ = [\"Engine\"]\n"
                    .to_string(),
            },
            Document {
                relative: "engine.py".to_string(),
                source: "class Engine:\n    pass\n".to_string(),
            },
            Document {
                relative: "consumer.py".to_string(),
                source: "from engine import Engine\n\nuse = Engine\n".to_string(),
            },
        ],
    )
    .expect("the graph builds");

    assert_eq!(graph.exports[0].bypasses.len(), 1);
    assert!(!graph.exports[0].bypasses[0].is_cycle_safe);
}

#[test]
fn a_relative_import_resolves_against_its_own_package() {
    let graph = build(
        "repo",
        &[
            Document {
                relative: "pkg/__init__.py".to_string(),
                source: String::new(),
            },
            Document {
                relative: "pkg/api.py".to_string(),
                source: "from .models import User\n".to_string(),
            },
            Document {
                relative: "pkg/models.py".to_string(),
                source: "class User:\n    pass\n".to_string(),
            },
        ],
    )
    .expect("the graph builds");

    assert!(graph.edges.iter().any(|edge| edge.kind == EdgeKind::Import
        && edge.source == "python:module:pkg.api"
        && edge.target == "python:module:pkg.models"));
}

#[test]
fn an_import_from_a_stub_reaches_its_public_declaration() {
    let graph = build(
        "repo",
        &[
            Document {
                relative: "pkg/__init__.py".to_string(),
                source: String::new(),
            },
            Document {
                relative: "pkg/native.pyi".to_string(),
                source: "class AnalysisSession: ...\n".to_string(),
            },
            Document {
                relative: "pkg/api.py".to_string(),
                source: "from .native import AnalysisSession\n".to_string(),
            },
        ],
    )
    .expect("the graph builds");
    let summaries = reach(&graph);
    let stub = summaries
        .iter()
        .find(|item| item.path == "pkg/native.pyi")
        .expect("the stub contributes reach facts");
    let declaration = stub
        .declarations
        .iter()
        .find(|item| item.qualname == "pkg.native.AnalysisSession")
        .expect("the stub class is declared");

    assert_eq!(declaration.references.other_file_references, 1);
}

#[test]
fn a_relative_import_beyond_its_package_never_becomes_an_absolute_one() {
    let graph = build(
        "repo",
        &[
            Document {
                relative: "pkg/__init__.py".to_string(),
                source: String::new(),
            },
            Document {
                relative: "pkg/api.py".to_string(),
                source: "from ..models import User\n".to_string(),
            },
            Document {
                relative: "models.py".to_string(),
                source: "class User:\n    pass\n".to_string(),
            },
        ],
    )
    .expect("the graph builds");

    assert!(graph.edges.iter().all(|edge| {
        edge.source != "python:module:pkg.api" || edge.target != "python:module:models"
    }));
    assert!(
        graph
            .nodes
            .iter()
            .any(|node| node.kind == NodeKind::UnresolvedSymbol
                && node.qualname.ends_with("::..models.User"))
    );
}
