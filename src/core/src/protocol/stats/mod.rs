use serde::Serialize;

mod graph_size;
mod timing;

pub use graph_size::GraphSize;
pub use timing::Timing;

/// What the kernel actually did and how much time it spent.
#[derive(Clone, Debug, Default, Serialize)]
pub struct Stats {
    pub file_count: usize,
    pub byte_count: usize,
    pub fact_count: usize,
    pub parse_failure_count: usize,
    #[serde(flatten)]
    pub timing: Timing,
    #[serde(flatten)]
    pub graph: GraphSize,
    pub repository_fingerprint: String,
}
