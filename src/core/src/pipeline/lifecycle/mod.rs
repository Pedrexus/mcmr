use crate::discovery;
use crate::graph::Graph;
use crate::protocol::{Request, Stats, Timing};
use std::time::Instant;

pub(super) fn discover_repository(
    request: &Request,
) -> Result<(discovery::Scope, discovery::Inventory, u128), String> {
    let started = Instant::now();
    let scope = discovery::Scope::of(std::path::Path::new(&request.root), &request.suffixes);
    let inventory = discovery::collect(request, &scope)?;
    Ok((scope, inventory, started.elapsed().as_nanos()))
}

pub(super) fn initial_stats(
    inventory: &discovery::Inventory,
    discovery_nanoseconds: u128,
) -> Stats {
    Stats {
        file_count: inventory.documents.len(),
        byte_count: inventory
            .documents
            .iter()
            .map(|document| document.source.len())
            .sum(),
        timing: Timing {
            discovery_nanoseconds,
            ..Timing::default()
        },
        repository_fingerprint: inventory.fingerprint.clone(),
        ..Stats::default()
    }
}

pub(super) fn complete_stats(
    stats: &mut Stats,
    graph: &Option<Graph>,
    graph_nanoseconds: u128,
    fact_count: usize,
) {
    if let Some(built) = graph {
        stats.graph.node_count = built.nodes.len();
        stats.graph.edge_count = built.edges.len();
    }
    stats.timing.graph_nanoseconds = graph_nanoseconds;
    stats.fact_count = fact_count;
}
