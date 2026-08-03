use super::super::contracts::{Edge, EdgeKind, Language, Node, NodeKind, Resolution, Visibility};
use super::primitives::{ExactEdge, node, relate};
use crate::discovery::Document;
use crate::graph::naming::Naming;
use std::collections::{BTreeMap, BTreeSet};

/// Place the repository, its directories, files, and declared modules.
pub(crate) fn workspace(
    root: &str,
    documents: &[Document],
    naming: &Naming,
) -> (BTreeMap<String, Node>, Vec<Edge>) {
    Workspace::collect(root, documents, naming)
}

struct Workspace<'a> {
    documents: &'a [Document],
    naming: &'a Naming,
    nodes: BTreeMap<String, Node>,
    edges: Vec<Edge>,
    placed: BTreeSet<(String, String)>,
}

impl<'a> Workspace<'a> {
    fn collect(
        root: &str,
        documents: &'a [Document],
        naming: &'a Naming,
    ) -> (BTreeMap<String, Node>, Vec<Edge>) {
        let mut workspace = Self::new(documents, naming);
        workspace.repository(root);
        (workspace.nodes, workspace.edges)
    }

    fn is_package(path: &str) -> bool {
        [
            "__init__.py",
            "/mod.rs",
            "/lib.rs",
            "/index.ts",
            "/index.tsx",
        ]
        .iter()
        .any(|suffix| path.ends_with(suffix))
    }

    fn new(documents: &'a [Document], naming: &'a Naming) -> Self {
        Self {
            documents,
            naming,
            nodes: BTreeMap::new(),
            edges: Vec::new(),
            placed: BTreeSet::new(),
        }
    }

    fn place(kind: NodeKind, path: &str) -> Node {
        Node::new(
            format!("path:{}:{path}", kind.label()),
            kind,
            None,
            Visibility::Public,
            path.to_string(),
        )
    }

    fn connect(&mut self, relation: ExactEdge<'_>) {
        if self
            .placed
            .insert((relation.source.to_string(), relation.target.to_string()))
        {
            relate(&mut self.edges, relation);
        }
    }

    fn directories(&mut self, document: &Document, repository: &str) -> String {
        let mut owner = repository.to_string();
        let parts = document.relative.split('/').collect::<Vec<_>>();
        for depth in 1..parts.len() {
            let entry = Self::place(NodeKind::Directory, &parts[..depth].join("/"));
            let entry_id = entry.id.clone();
            self.nodes.entry(entry_id.clone()).or_insert(entry);
            self.connect(ExactEdge {
                source: &owner,
                target: &entry_id,
                kind: EdgeKind::Contain,
                path: &document.relative,
                line: 1,
            });
            owner = entry_id;
        }
        owner
    }

    fn document(&mut self, document: &Document, repository: &str) {
        let owner = self.directories(document, repository);
        let file = self.file(document, &owner);
        self.module(document, &file);
    }

    fn file(&mut self, document: &Document, owner: &str) -> String {
        let mut file = Self::place(NodeKind::File, &document.relative);
        file.path = Some(document.relative.clone());
        file.language = Language::of(&document.relative);
        let file_id = file.id.clone();
        self.nodes.entry(file_id.clone()).or_insert(file);
        self.connect(ExactEdge {
            source: owner,
            target: &file_id,
            kind: EdgeKind::Contain,
            path: &document.relative,
            line: 1,
        });
        file_id
    }

    fn module(&mut self, document: &Document, file: &str) {
        let Some((language, named)) = self.naming.module(&document.relative) else {
            return;
        };
        let mut module = node(language, NodeKind::Module, &named);
        module.path = Some(document.relative.clone());
        module.is_package = Self::is_package(&document.relative);
        let module_id = module.id.clone();
        self.nodes.entry(module_id.clone()).or_insert(module);
        self.edges.push(Edge {
            source: file.to_string(),
            target: module_id,
            kind: EdgeKind::Define,
            path: document.relative.clone(),
            line: 1,
            resolution: Resolution::Exact,
        });
    }

    fn repository(&mut self, root: &str) {
        let name = root
            .trim_end_matches('/')
            .rsplit('/')
            .next()
            .unwrap_or(root);
        let repository = Self::place(NodeKind::Repository, name);
        let repository_id = repository.id.clone();
        self.nodes.insert(repository_id.clone(), repository);
        for document in self.documents {
            self.document(document, &repository_id);
        }
    }
}
