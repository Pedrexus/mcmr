use ruff_text_size::TextRange;
use serde_json::Value;

pub(super) struct SyntaxNodeValue<'syntax> {
    pub(super) kind: &'syntax str,
    pub(super) name: &'syntax str,
    pub(super) range: TextRange,
    pub(super) children: Vec<Value>,
}
