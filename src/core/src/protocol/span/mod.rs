use serde::{Deserialize, Serialize};

/// One source location in the shape the Python `SourceSpan` model validates.
#[derive(Clone, Debug, Default, Deserialize, Serialize)]
pub struct Span {
    pub path: String,
    pub start_line: usize,
    pub start_column: usize,
    pub end_line: usize,
    pub end_column: usize,
}
