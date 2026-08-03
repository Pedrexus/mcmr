use serde::Serialize;

/// Size of the repository dependency graph the kernel retained.
#[derive(Clone, Debug, Default, Serialize)]
pub struct GraphSize {
    pub node_count: usize,
    pub edge_count: usize,
}
