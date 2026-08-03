use serde::Serialize;

/// What one relationship between two nodes is.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum EdgeKind {
    Contain,
    Define,
    Import,
    Call,
    Instantiate,
    Inherit,
    Typed,
    Access,
}
