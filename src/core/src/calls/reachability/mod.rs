use crate::graph;
use crate::source::is_test_path;
use std::collections::{BTreeMap, BTreeSet};

pub(crate) struct TestReachability {
    calls: BTreeMap<String, Vec<String>>,
    canonical: BTreeMap<String, String>,
    owners: BTreeMap<(String, usize), String>,
    production: BTreeMap<String, String>,
}

impl TestReachability {
    pub(crate) fn new(repository: &graph::Graph) -> Self {
        let internal = repository
            .nodes
            .iter()
            .filter(|node| node.path.is_some())
            .map(|node| (node.qualname.as_str(), node.id.as_str()))
            .collect::<BTreeMap<_, _>>();
        let routes = repository
            .exports
            .iter()
            .map(|export| {
                (
                    format!("{}.{}", export.module, export.name),
                    export.target.as_str(),
                )
            })
            .collect::<BTreeMap<_, _>>();
        let mut aliases = BTreeMap::new();
        for public in routes.keys() {
            let mut target = public.as_str();
            let mut seen = BTreeSet::new();
            while seen.insert(target) {
                if let Some(internal_target) = internal.get(target) {
                    aliases.insert(public.clone(), (*internal_target).to_string());
                    break;
                }
                let Some(next) = routes.get(target) else {
                    break;
                };
                target = next;
            }
        }
        let canonical = repository
            .nodes
            .iter()
            .filter_map(|node| {
                aliases
                    .get(&node.qualname)
                    .map(|target| (node.id.clone(), target.clone()))
            })
            .collect::<BTreeMap<_, _>>();
        let mut calls: BTreeMap<String, Vec<String>> = BTreeMap::new();
        for edge in repository.edges.iter().filter(|edge| {
            matches!(
                edge.kind,
                graph::EdgeKind::Access | graph::EdgeKind::Call | graph::EdgeKind::Instantiate
            )
        }) {
            calls
                .entry(edge.source.clone())
                .or_default()
                .push(canonical.get(&edge.target).unwrap_or(&edge.target).clone());
        }
        let owners = repository
            .nodes
            .iter()
            .filter_map(|node| {
                let path = node.path.as_deref().filter(|path| is_test_path(path))?;
                let line = node.line?;
                matches!(
                    node.kind,
                    graph::NodeKind::Function | graph::NodeKind::Method
                )
                .then(|| ((path.to_string(), line), node.id.clone()))
            })
            .collect();
        let production = repository
            .nodes
            .iter()
            .filter_map(|node| {
                node.path.as_deref().filter(|path| !is_test_path(path))?;
                matches!(
                    node.kind,
                    graph::NodeKind::Class | graph::NodeKind::Function | graph::NodeKind::Method
                )
                .then(|| (node.id.clone(), node.qualname.clone()))
            })
            .collect();
        Self {
            calls,
            canonical,
            owners,
            production,
        }
    }

    pub(super) fn direct(&self, path: &str, line: usize, targets: &[String]) -> Vec<String> {
        self.roots(path, line, targets)
            .iter()
            .filter_map(|target| self.production.get(target))
            .cloned()
            .collect::<BTreeSet<_>>()
            .into_iter()
            .collect()
    }

    pub(super) fn reachable(&self, path: &str, line: usize, targets: &[String]) -> Vec<String> {
        let mut seen = BTreeSet::new();
        let mut pending = self.roots(path, line, targets);
        let mut production = BTreeSet::new();
        while let Some(target) = pending.pop() {
            if !seen.insert(target.clone()) {
                continue;
            }
            if let Some(name) = self.production.get(&target) {
                production.insert(name.clone());
            }
            pending.extend(self.calls.get(&target).into_iter().flatten().cloned());
        }
        production.into_iter().collect()
    }

    fn roots(&self, path: &str, line: usize, targets: &[String]) -> Vec<String> {
        self.owners
            .get(&(path.to_string(), line))
            .into_iter()
            .flat_map(|owner| self.calls.get(owner).into_iter().flatten().cloned())
            .chain(
                targets
                    .iter()
                    .map(|target| self.canonical.get(target).unwrap_or(target).clone()),
            )
            .collect::<BTreeSet<_>>()
            .into_iter()
            .collect()
    }
}
