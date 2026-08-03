use serde::Serialize;

/// What one module depends on and what depends on it.
#[derive(Clone, Debug, Default, Serialize)]
pub struct Coupling {
    pub module: String,
    pub afferent_count: usize,
    pub efferent_count: usize,
}
