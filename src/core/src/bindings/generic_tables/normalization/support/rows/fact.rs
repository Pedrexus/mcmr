use super::super::scalar::{ScalarKey, ScalarValue};
use serde_json::{Map, Value};
use std::collections::HashMap;

mod language;
mod source;
mod span;

use language::fact_language;
use source::{fact_span, source_coordinates, source_path};
use span::FactSpan;

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
        let path = source_path(fact_id, span)?;
        let [start_line, start_column, end_line, end_column] = source_coordinates(span)?;
        Ok(Self {
            fact_order,
            fact_id: fact_id.to_string(),
            span: FactSpan {
                path: path.to_string(),
                start_line,
                start_column,
                end_line,
                end_column,
            },
            language: fact_language(stated.get("language"), fact_id)?.map(str::to_string),
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

fn fact_object(fact_order: u64, fact: &Value) -> Result<&Map<String, Value>, String> {
    fact.as_object()
        .ok_or_else(|| format!("fact {fact_order} is not an object"))
}
