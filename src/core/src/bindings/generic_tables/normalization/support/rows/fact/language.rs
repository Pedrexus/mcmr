use serde_json::Value;

pub(super) fn fact_language<'value>(
    stated: Option<&'value Value>,
    fact_id: &str,
) -> Result<Option<&'value str>, String> {
    Ok(match stated {
        Some(Value::String(language)) => Some(language),
        Some(Value::Null) | None => None,
        Some(_) => return Err(format!("fact {fact_id} language is not text")),
    })
}
