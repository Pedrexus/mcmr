use graph::dependency_graphs;
use traversal::finish_order;

mod assignment;
mod graph;
mod traversal;

/// Partition every module named by an import edge into strongly connected components.
pub(super) fn strong_components(
    edges: &[(String, String)],
) -> std::collections::BTreeMap<&str, u64> {
    let (forward, reverse) = dependency_graphs(edges);
    assignment::assign_components(&reverse, finish_order(&forward))
}
