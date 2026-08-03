use crate::source::{Source, is_test_path};
use serde_json::{Value, json};

pub(super) fn base(source: &Source, key: &str, range: ruff_text_size::TextRange) -> Value {
    json!({"key": key, "span": source.span(range), "language": "python"})
}

/// Whether pytest would collect one file, which is what makes its functions tests.
pub(super) fn is_test_module(source: &Source) -> bool {
    is_test_path(&source.relative)
}
