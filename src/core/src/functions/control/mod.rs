use serde::Serialize;

/// One control structure inside a callable and its visible nesting depth.
#[derive(Clone, Debug, Serialize)]
pub struct ControlIncrement {
    pub kind: String,
    pub nesting_depth: usize,
}

impl ControlIncrement {
    pub fn new(kind: &str, nesting_depth: usize) -> Self {
        Self {
            kind: kind.to_string(),
            nesting_depth,
        }
    }
}
