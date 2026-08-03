use super::expression::StringExpression;
use serde::Serialize;
use serde_json::Value;

/// One file and every string expression it folds together.
#[derive(Clone, Debug, Serialize)]
pub struct StringExpressionRecord {
    pub key: String,
    pub span: crate::protocol::Span,
    pub language: String,
    pub expressions: Vec<StringExpression>,
}

impl StringExpressionRecord {
    /// Serialize one typed provider record for the independent JSON protocol.
    pub fn into_json(self) -> Value {
        serde_json::to_value(self).expect("a typed string expression record must serialize")
    }
}
