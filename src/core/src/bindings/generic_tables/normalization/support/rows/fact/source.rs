use serde_json::{Map, Value};

pub(super) fn fact_span<'fact>(
    fact_id: &str,
    stated: &'fact Map<String, Value>,
) -> Result<&'fact Map<String, Value>, String> {
    stated
        .get("span")
        .and_then(Value::as_object)
        .ok_or_else(|| format!("fact {fact_id} has no source span"))
}

pub(super) fn source_coordinates(span: &Map<String, Value>) -> Result<[u64; 4], String> {
    Ok([
        span_integer(span, "start_line", 1)?,
        span_integer(span, "start_column", 0)?,
        span_integer(span, "end_line", 1)?,
        span_integer(span, "end_column", 0)?,
    ])
}

pub(super) fn source_path<'span>(
    fact_id: &str,
    span: &'span Map<String, Value>,
) -> Result<&'span str, String> {
    span.get("path")
        .and_then(Value::as_str)
        .ok_or_else(|| format!("fact {fact_id} has no source path"))
}

fn span_integer(span: &Map<String, Value>, name: &str, default: u64) -> Result<u64, String> {
    match span.get(name) {
        None => Ok(default),
        Some(value) => value
            .as_u64()
            .ok_or_else(|| format!("source span {name} is not a nonnegative integer")),
    }
}
