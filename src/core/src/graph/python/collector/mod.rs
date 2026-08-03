use crate::graph::construction::identity;
use crate::graph::contracts::{Language, NodeKind, Stated};
use crate::source::Source;
use ruff_python_ast::{ModModule, Stmt};
use ruff_python_parser::parse_module;
use std::collections::{BTreeMap, BTreeSet};

mod access_request;
mod declarations;
mod expressions;
mod owner;
mod reference_request;
mod state;
mod statements;
mod support;

use access_request::AccessRequest;
use owner::Owner;
use reference_request::ReferenceRequest;
use state::GraphState;

/// Collect every definition and reference one module states.
pub(super) struct Collector {
    source: Source,
    module: String,
    is_package: bool,
    graph: GraphState,
    owners: Vec<Owner>,
    classes: Vec<String>,
    types: Vec<BTreeMap<String, String>>,
}

impl Collector {
    pub(super) fn collect(source: Source, module: &str) -> Option<Stated> {
        let parsed = parse_module(&source.text).ok()?;
        let exports = crate::python::imports::exported_names(parsed.syntax())
            .into_iter()
            .collect::<BTreeSet<_>>();
        let export_nodes = crate::python::imports::exported_nodes(&source, parsed.syntax());
        let mut collector = Self::new(source, module.to_string());
        collector.module(parsed.syntax());
        Some(Stated {
            nodes: collector.graph.nodes,
            edges: collector.graph.edges,
            references: collector.graph.references,
            export_references: collector.graph.export_references,
            aliases: collector.graph.aliases,
            exports,
            export_nodes,
        })
    }

    fn new(source: Source, module: String) -> Self {
        let owners = vec![Self::root_owner(&module)];
        Self {
            is_package: source.relative.ends_with("__init__.py"),
            source,
            module,
            graph: GraphState::default(),
            owners,
            classes: Vec::new(),
            types: vec![BTreeMap::new()],
        }
    }

    fn root_owner(module: &str) -> Owner {
        Owner {
            id: identity(Language::Python, NodeKind::Module, module),
            kind: NodeKind::Module,
            qualname: module.to_string(),
        }
    }

    fn body(&mut self, body: &[Stmt]) {
        for statement in body {
            self.statement(statement);
        }
    }

    fn module(&mut self, module: &ModModule) {
        self.body(&module.body);
    }
}
