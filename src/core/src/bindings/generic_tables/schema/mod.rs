use serde_json::{Map, Value};

pub(super) use kind::ScalarKind;

pub(super) mod compiler;
mod kind;
mod shape;

pub(crate) type ObjectSchema = shape::ObjectSchema<Schema>;
pub(super) type Shape = shape::Shape<Schema, ObjectSchema>;

#[derive(Clone, Debug)]
pub(super) struct Schema {
    pub(super) shape: Shape,
    pub(super) default: Option<Value>,
}

pub(super) fn stated_value<'a>(
    stated: Option<&'a Map<String, Value>>,
    name: &str,
    concise_root: Option<&'a Value>,
) -> Option<&'a Value> {
    if name == "root" {
        concise_root.or_else(|| stated.and_then(|row| row.get(name)))
    } else {
        stated.and_then(|row| row.get(name))
    }
}

pub(super) fn effective<'a>(schema: &'a Schema, actual: Option<&'a Value>) -> Option<&'a Value> {
    match actual {
        Some(Value::Null) | None => schema.default.as_ref(),
        stated => stated,
    }
}

fn scalar(kind: ScalarKind) -> Schema {
    Schema {
        shape: Shape::Scalar(kind),
        default: None,
    }
}

fn union_variants(raw: &Map<String, Value>) -> Option<&Vec<Value>> {
    ["anyOf", "oneOf", "allOf"]
        .into_iter()
        .find_map(|name| raw.get(name).and_then(Value::as_array))
}
