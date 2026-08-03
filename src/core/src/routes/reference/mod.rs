use serde::Serialize;

/// One place that names the path of a route as a literal.
#[derive(Clone, Debug, Serialize)]
pub struct Reference {
    pub path: String,
    pub language: String,
    pub line: usize,
}
