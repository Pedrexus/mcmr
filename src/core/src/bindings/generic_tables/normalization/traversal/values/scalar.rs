use super::super::super::super::schema::{ScalarKind, Schema, Shape, effective};
use super::super::super::support::{ScalarKey, ScalarValue};
use serde_json::Value;
use std::collections::HashMap;

pub(super) fn append_scalar(
    row: &mut HashMap<ScalarKey, ScalarValue>,
    path: &str,
    schema: &Schema,
    actual: Option<&Value>,
) -> Result<(), String> {
    if let Some(value) = scalar_value(schema, actual)? {
        let kind = match value {
            ScalarValue::Boolean(_) => ScalarKind::Boolean,
            ScalarValue::Float(_) => ScalarKind::Float,
            ScalarValue::Integer(_) => ScalarKind::Integer,
            ScalarValue::String(_) => ScalarKind::String,
        };
        row.insert(
            ScalarKey {
                path: path.to_string(),
                kind,
            },
            value,
        );
    }
    Ok(())
}

pub(crate) fn scalar_value(
    schema: &Schema,
    actual: Option<&Value>,
) -> Result<Option<ScalarValue>, String> {
    let Some(value) = effective(schema, actual).filter(|value| !value.is_null()) else {
        return Ok(None);
    };
    match &schema.shape {
        Shape::Scalar(kind) => typed_scalar(*kind, value).map(Some),
        Shape::Union(variants) => union_scalar(variants, value).map(Some),
        _ => Err("table value schema is not scalar".to_string()),
    }
}

fn typed_scalar(kind: ScalarKind, value: &Value) -> Result<ScalarValue, String> {
    match kind {
        ScalarKind::Boolean => typed_boolean(value),
        ScalarKind::Float => typed_float(value),
        ScalarKind::Integer => typed_integer(value),
        ScalarKind::String => typed_string(value),
    }
}

fn typed_boolean(value: &Value) -> Result<ScalarValue, String> {
    value
        .as_bool()
        .map(ScalarValue::Boolean)
        .ok_or_else(|| "table Boolean value has another type".to_string())
}

fn typed_float(value: &Value) -> Result<ScalarValue, String> {
    value
        .as_f64()
        .map(ScalarValue::Float)
        .ok_or_else(|| "table float value has another type".to_string())
}

fn typed_integer(value: &Value) -> Result<ScalarValue, String> {
    value
        .as_i64()
        .or_else(|| value.as_u64().and_then(|number| i64::try_from(number).ok()))
        .map(ScalarValue::Integer)
        .ok_or_else(|| "table integer value is outside signed 64-bit range".to_string())
}

fn typed_string(value: &Value) -> Result<ScalarValue, String> {
    value
        .as_str()
        .map(|text| ScalarValue::String(text.to_string()))
        .ok_or_else(|| "table string value has another type".to_string())
}

fn union_scalar(variants: &[Schema], value: &Value) -> Result<ScalarValue, String> {
    for variant in variants {
        if let Shape::Scalar(kind) = variant.shape
            && ScalarKind::of(value) == Some(kind)
        {
            return typed_scalar(kind, value);
        }
    }
    Err("union value does not match any scalar table type".to_string())
}
