use super::span::Span;
use serde::{Deserialize, Serialize};

/// One resolved syntax node in the shape the Python `NodeRef` model validates.
#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct Node {
    pub id: String,
    pub span: Span,
    pub kind: String,
    pub text: String,
}
