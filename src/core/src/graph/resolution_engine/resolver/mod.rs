use super::attachment::Attachment;
use super::context::ResolutionContext;
use crate::graph::contracts::{Edge, EdgeKind, Node, NodeKind, Reference};
use std::collections::{BTreeMap, BTreeSet};

mod support;

pub(crate) use support::{attach, is_builtin};
pub use support::{expand, stray};
use support::{is_dotted_path, through_reexport};

pub(crate) fn resolve(reference: &Reference, context: ResolutionContext<'_>) {
    Resolver {
        reference,
        symbols: context.symbols,
        aliases: context.aliases,
        nodes: context.nodes,
        edges: context.edges,
    }
    .run();
}

struct Resolver<'a> {
    reference: &'a Reference,
    symbols: &'a BTreeSet<String>,
    aliases: &'a BTreeMap<String, BTreeMap<String, String>>,
    nodes: &'a mut BTreeMap<String, Node>,
    edges: &'a mut Vec<Edge>,
}

impl Resolver<'_> {
    pub(super) fn run(mut self) {
        let expanded = self.expanded();
        let candidates = self.candidates(&expanded);
        if self.attach(&candidates, self.reference.kind) {
            return;
        }
        self.attach_receiver();
        let (kind, qualname) = self.placeholder(expanded);
        stray(self.reference, kind, &qualname, self.nodes, self.edges);
    }

    fn attach(&mut self, candidates: &[String], relation_kind: EdgeKind) -> bool {
        attach(
            Attachment {
                reference: self.reference,
                candidates,
                symbols: self.symbols,
                relation_kind,
            },
            self.nodes,
            self.edges,
        )
    }

    fn attach_receiver(&mut self) {
        if self.reference.kind != EdgeKind::Call {
            return;
        }
        let Some((receiver, _)) = self.reference.expression.rsplit_once('.') else {
            return;
        };
        let expanded = self.expand(receiver);
        let candidates = [
            format!("{}.{}", self.reference.module, expanded),
            expanded,
            receiver.to_string(),
        ];
        self.attach(&candidates, EdgeKind::Access);
    }

    fn candidates(&self, expanded: &str) -> Vec<String> {
        if self.reference.kind == EdgeKind::Import {
            self.import_candidates(expanded)
        } else {
            self.symbol_candidates(expanded)
        }
    }

    fn expand(&self, expression: &str) -> String {
        self.local().map_or_else(
            || expression.to_string(),
            |aliases| expand(expression, aliases),
        )
    }

    fn expanded(&self) -> String {
        if self.reference.kind == EdgeKind::Import {
            self.reference.expression.clone()
        } else {
            self.expand(&self.reference.expression)
        }
    }

    fn external_roots(&self) -> BTreeSet<&str> {
        self.local()
            .into_iter()
            .flat_map(BTreeMap::values)
            .map(|target| target.split('.').next().unwrap_or(target))
            .collect()
    }

    fn import_candidates(&self, expanded: &str) -> Vec<String> {
        let mut candidates = Vec::new();
        candidates.extend(through_reexport(expanded, self.aliases, self.symbols));
        let parts = expanded.split('.').collect::<Vec<_>>();
        candidates.extend((1..=parts.len()).rev().map(|size| parts[..size].join(".")));
        candidates
    }

    fn import_placeholder(&self, expanded: String) -> (NodeKind, String) {
        if expanded.starts_with('.') {
            (
                NodeKind::UnresolvedSymbol,
                format!("{}::{expanded}", self.reference.module),
            )
        } else {
            (
                NodeKind::ExternalModule,
                expanded.split('.').next().unwrap_or(&expanded).to_string(),
            )
        }
    }

    fn local(&self) -> Option<&BTreeMap<String, String>> {
        self.aliases.get(&self.reference.module)
    }

    fn owned_candidate(&self, members: Option<&str>) -> Option<String> {
        match (
            &self.reference.resolution.owner,
            self.reference.expression.split('.').next(),
        ) {
            (Some(owner), Some("self" | "cls")) => {
                members.map(|member| format!("{owner}.{member}"))
            }
            _ => None,
        }
    }

    fn placeholder(&self, expanded: String) -> (NodeKind, String) {
        if self.reference.kind == EdgeKind::Import {
            return self.import_placeholder(expanded);
        }
        self.symbol_placeholder(expanded)
    }

    fn symbol_candidates(&self, expanded: &str) -> Vec<String> {
        let members = self
            .reference
            .expression
            .split_once('.')
            .map(|(_, rest)| rest);
        let mut candidates = self.typed_candidates(members);
        candidates.extend([
            self.owned_candidate(members).unwrap_or_default(),
            format!("{}.{expanded}", self.reference.module),
            expanded.to_string(),
            self.reference.expression.clone(),
        ]);
        candidates
    }

    fn symbol_placeholder(&self, expanded: String) -> (NodeKind, String) {
        let head = expanded.split('.').next().unwrap_or(&expanded);
        if !self.reference.expression.contains('.') && is_builtin(&self.reference.expression) {
            return (
                NodeKind::ExternalSymbol,
                format!("builtins.{}", self.reference.expression),
            );
        }
        if self.external_roots().contains(head) && is_dotted_path(&expanded) {
            return (NodeKind::ExternalSymbol, expanded);
        }
        (
            NodeKind::UnresolvedSymbol,
            format!("{}::{}", self.reference.module, self.reference.expression),
        )
    }

    fn typed_candidates(&self, members: Option<&str>) -> Vec<String> {
        match (&self.reference.resolution.receiver_type, members) {
            (Some(kind), Some(member)) => {
                let resolved = self.expand(kind);
                vec![
                    format!("{resolved}.{member}"),
                    format!("{}.{resolved}.{member}", self.reference.module),
                ]
            }
            _ => Vec::new(),
        }
    }
}
