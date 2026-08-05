use super::fact_span::FactSpan;
use super::scalar::{ScalarKey, ScalarValue};
use serde_json::{Map, Value};
use std::collections::HashMap;

pub(crate) struct FactRow {
    pub(crate) fact_order: u64,
    pub(crate) fact_id: String,
    pub(crate) span: FactSpan,
    pub(crate) language: Option<String>,
    pub(crate) scalars: HashMap<ScalarKey, ScalarValue>,
}

impl FactRow {
    pub(crate) fn parse(fact_order: u64, fact: &Value) -> Result<Self, String> {
        let stated = fact_object(fact_order, fact)?;
        let fact_id = fact_id(fact_order, stated)?;
        let span = fact_span(fact_id, stated)?;
        Ok(Self {
            fact_order,
            fact_id: fact_id.to_string(),
            span,
            language: fact_language(stated.get("language"), fact_id)?,
            scalars: HashMap::new(),
        })
    }
}

fn fact_id(fact_order: u64, stated: &Map<String, Value>) -> Result<&str, String> {
    stated
        .get("key")
        .and_then(Value::as_str)
        .ok_or_else(|| format!("fact {fact_order} has no string key"))
}

fn fact_language(stated: Option<&Value>, fact_id: &str) -> Result<Option<String>, String> {
    Ok(match stated {
        Some(Value::String(language)) => Some(language.clone()),
        Some(Value::Null) | None => None,
        Some(_) => return Err(format!("fact {fact_id} language is not text")),
    })
}

fn fact_object(fact_order: u64, fact: &Value) -> Result<&Map<String, Value>, String> {
    fact.as_object()
        .ok_or_else(|| format!("fact {fact_order} is not an object"))
}

fn fact_span(fact_id: &str, stated: &Map<String, Value>) -> Result<FactSpan, String> {
    let span = stated
        .get("span")
        .and_then(Value::as_object)
        .ok_or_else(|| format!("fact {fact_id} has no source span"))?;
    let path = span
        .get("path")
        .and_then(Value::as_str)
        .ok_or_else(|| format!("fact {fact_id} has no source path"))?;
    let [start_line, start_column, end_line, end_column] = source_coordinates(span)?;
    Ok(FactSpan {
        path: path.to_string(),
        start_line,
        start_column,
        end_line,
        end_column,
    })
}

fn source_coordinates(span: &Map<String, Value>) -> Result<[u64; 4], String> {
    Ok([
        span_integer(span, "start_line", 1)?,
        span_integer(span, "start_column", 0)?,
        span_integer(span, "end_line", 1)?,
        span_integer(span, "end_column", 0)?,
    ])
}

fn span_integer(span: &Map<String, Value>, name: &str, default: u64) -> Result<u64, String> {
    match span.get(name) {
        None => Ok(default),
        Some(value) => value
            .as_u64()
            .ok_or_else(|| format!("source span {name} is not a nonnegative integer")),
    }
}
