use super::super::frames::joined;
use super::super::kind::ContainerKind;
use super::super::path::{FieldContext, RowPath};
use super::super::support::{ScalarKey, ScalarValue};
use crate::bindings::generic_tables::schema::{
    ObjectSchema, ScalarKind, Schema, Shape, stated_value,
};
use serde_json::{Map, Value};
use std::collections::HashMap;

mod scalar;

use scalar::append_scalar;
pub(super) use scalar::scalar_value;

pub(super) fn append_scalar_field(
    context: FieldContext<'_>,
    scalars: &mut HashMap<ScalarKey, ScalarValue>,
) -> Result<(), String> {
    append_scalar(
        scalars,
        &joined([context.path.scalar, context.name]),
        context.field,
        context.actual,
    )
}

pub(super) fn array_entries(actual: &Value) -> &[Value] {
    actual
        .as_array()
        .expect("a nested array was validated before traversal")
}

pub(super) fn is_root_metadata(path: RowPath<'_>, name: &str) -> bool {
    path.scalar.is_empty()
        && path.relation.is_empty()
        && matches!(name, "key" | "span" | "language")
}

pub(super) fn map_entries(actual: &Value) -> &Map<String, Value> {
    actual
        .as_object()
        .expect("a nested map was validated before traversal")
}

pub(super) fn object_schema(
    schema: &Schema,
) -> Result<&crate::bindings::generic_tables::schema::ObjectSchema, String> {
    let Shape::Object(object) = &schema.shape else {
        return Err("a normalized table row schema is not an object".to_string());
    };
    Ok(object)
}

pub(super) fn stated_field<'value>(
    context: FieldContext<'value>,
    stated: Option<&'value Map<String, Value>>,
    object: &ObjectSchema,
    concise: Option<&'value Value>,
) -> Result<FieldContext<'value>, String> {
    let held = stated_value(stated, context.name, concise);
    if held.is_none() && object.required.contains(context.name) && context.field.default.is_none()
    {
        return Err(format!(
            "relation {} is missing required field {}",
            context.path.relation, context.name
        ));
    }
    Ok(context.with_actual(held))
}

pub(super) fn container_length(
    schema: &Schema,
    actual: &Value,
    relation: &str,
) -> Result<u64, String> {
    match &schema.shape {
        Shape::Array(_) => actual.as_array().map(Vec::len),
        Shape::Map(_) => actual.as_object().map(Map::len),
        _ => None,
    }
    .map(|length| length as u64)
    .ok_or_else(|| format!("relation {relation} nested container has another type"))
}

pub(super) fn concise_root<'value>(
    actual: Option<&'value Value>,
    object: &ObjectSchema,
    stated: Option<&Map<String, Value>>,
) -> Option<&'value Value> {
    actual.filter(|value| {
        stated.is_none()
            && object.fields.len() == 1
            && object.fields.contains_key("root")
            && (value.is_array() || value.is_object())
    })
}

pub(super) fn append_container_metadata(
    row: &mut HashMap<ScalarKey, ScalarValue>,
    path: &str,
    actual: Option<&Value>,
    kind: ContainerKind,
) -> Result<(), String> {
    let length = container_metadata_length(actual, kind, path)?;
    row.insert(
        metadata_key([path, "present"], ScalarKind::Boolean),
        ScalarValue::Boolean(length.is_some()),
    );
    if let Some(length) = length {
        row.insert(
            metadata_key([path, "length"], ScalarKind::Integer),
            ScalarValue::Integer(length as i64),
        );
    }
    Ok(())
}

fn container_metadata_length(
    actual: Option<&Value>,
    kind: ContainerKind,
    path: &str,
) -> Result<Option<usize>, String> {
    let Some(actual) = actual.filter(|value| !value.is_null()) else {
        return Ok(None);
    };
    match kind {
        ContainerKind::Array => actual.as_array().map(Vec::len),
        ContainerKind::Map => actual.as_object().map(Map::len),
    }
    .map(Some)
    .ok_or_else(|| format!("container {path} has another type"))
}

fn metadata_key([path, name]: [&str; 2], kind: ScalarKind) -> ScalarKey {
    ScalarKey {
        path: format!("{path}.{name}"),
        kind,
    }
}
