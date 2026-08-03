use serde::Serialize;

/// Time the kernel spent in each repository analysis phase.
#[derive(Clone, Debug, Default, Serialize)]
pub struct Timing {
    pub discovery_nanoseconds: u128,
    pub extraction_nanoseconds: u128,
    pub graph_nanoseconds: u128,
}
