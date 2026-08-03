use serde::Serialize;

/// One place that reaches an artifact, and how sure the kernel is that it does.
#[derive(Clone, Debug, Serialize)]
pub(crate) struct Reference {
    pub path: String,
    pub language: String,
    pub line: usize,
}
