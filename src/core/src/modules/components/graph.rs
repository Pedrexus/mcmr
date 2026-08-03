use std::collections::BTreeMap;

pub(super) type DependencyGraph<'a> = BTreeMap<&'a str, Vec<&'a str>>;

pub(super) fn dependency_graphs(
    edges: &[(String, String)],
) -> (DependencyGraph<'_>, DependencyGraph<'_>) {
    let mut forward = DependencyGraph::new();
    let mut reverse = DependencyGraph::new();
    for (source, target) in edges {
        forward
            .entry(source.as_str())
            .or_default()
            .push(target.as_str());
        forward.entry(target.as_str()).or_default();
        reverse
            .entry(target.as_str())
            .or_default()
            .push(source.as_str());
        reverse.entry(source.as_str()).or_default();
    }
    for reached in forward.values_mut().chain(reverse.values_mut()) {
        reached.sort();
        reached.dedup();
    }
    (forward, reverse)
}
