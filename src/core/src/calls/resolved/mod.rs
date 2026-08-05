use crate::graph;
use std::collections::{BTreeMap, BTreeSet};

/// One graph answer joined back onto the syntax record for the same call site.
#[derive(Clone)]
pub(crate) struct ResolvedCall {
    pub(crate) target_id: String,
    pub(crate) qualified_name: String,
    pub(crate) resolution: graph::Resolution,
    pub(crate) is_external: bool,
    pub(crate) is_first_party: bool,
    pub(crate) is_standard_library: bool,
    pub(crate) is_constructor: bool,
}

/// Resolve repository graph calls once, indexed by their source line and order.
pub(crate) fn resolutions(
    graph: &graph::Graph,
    standard_library: &BTreeSet<&str>,
) -> BTreeMap<(String, usize), Vec<ResolvedCall>> {
    let nodes: BTreeMap<&str, &graph::Node> = graph
        .nodes
        .iter()
        .map(|node| (node.id.as_str(), node))
        .collect();
    let project_modules = graph
        .nodes
        .iter()
        .filter(|node| node.kind == graph::NodeKind::Module && node.path.is_some())
        .map(|node| node.qualname.as_str())
        .collect::<BTreeSet<_>>();
    let mut resolved: BTreeMap<(String, usize), Vec<ResolvedCall>> = BTreeMap::new();
    for edge in graph.edges.iter().filter(|edge| {
        matches!(
            edge.kind,
            graph::EdgeKind::Call | graph::EdgeKind::Instantiate
        )
    }) {
        let Some(target) = nodes.get(edge.target.as_str()) else {
            continue;
        };
        let root = target.qualname.split('.').next().unwrap_or_default();
        let first_party = edge.resolution == graph::Resolution::Exact
            || belongs_to_project(&target.qualname, &project_modules);
        let external = edge.resolution == graph::Resolution::External && !first_party;
        resolved
            .entry((edge.path.clone(), edge.line))
            .or_default()
            .push(ResolvedCall {
                target_id: target.id.clone(),
                qualified_name: target.qualname.clone(),
                resolution: edge.resolution,
                is_external: external,
                is_first_party: first_party,
                is_standard_library: external
                    && (root == "builtins" || standard_library.contains(root)),
                is_constructor: edge.kind == graph::EdgeKind::Instantiate,
            });
    }
    resolved
}

fn belongs_to_project(qualname: &str, modules: &BTreeSet<&str>) -> bool {
    modules.iter().any(|module| {
        qualname == *module
            || qualname
                .strip_prefix(*module)
                .is_some_and(|suffix| suffix.starts_with('.'))
    })
}

#[cfg(test)]
mod tests {
    use super::belongs_to_project;
    use std::collections::BTreeSet;

    #[test]
    fn an_unresolved_member_below_a_project_module_is_still_first_party() {
        let modules = BTreeSet::from(["mcmr.structure.change"]);

        assert!(belongs_to_project(
            "mcmr.structure.change.ProposedImport.parse",
            &modules
        ));
        assert!(!belongs_to_project("mcmr_external.parse", &modules));
    }
}
