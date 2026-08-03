use super::{ObjectSchema, ScalarKind, Schema, Shape, scalar, union_variants};
use serde_json::{Map, Value};
use std::cell::RefCell;
use std::collections::{BTreeMap, BTreeSet};

pub(crate) struct SchemaCompiler<'a> {
    pub(crate) root: &'a Value,
    pub(crate) resolving: RefCell<BTreeSet<String>>,
}

impl SchemaCompiler<'_> {
    pub(crate) fn compile(&self, source: &Value) -> Result<Schema, String> {
        let raw = source
            .as_object()
            .ok_or_else(|| "fact table schema node is not an object".to_string())?;
        let mut schema = if let Some(reference) = raw.get("$ref").and_then(Value::as_str) {
            self.reference(reference)?
        } else if let Some(variants) = union_variants(raw) {
            self.union(variants)?
        } else {
            self.typed(raw)?
        };
        if let Some(default) = raw.get("default") {
            schema.default = Some(default.clone());
        }
        Ok(schema)
    }

    fn array(&self, raw: &Map<String, Value>) -> Result<Schema, String> {
        let item = if let Some(item) = raw.get("items") {
            self.compile(item)?
        } else if let Some(items) = raw.get("prefixItems").and_then(Value::as_array) {
            self.merge(
                items
                    .iter()
                    .map(|item| self.compile(item))
                    .collect::<Result<Vec<_>, _>>()?,
            )?
        } else {
            return Err("fact table array schema has no item type".to_string());
        };
        Ok(Schema {
            shape: Shape::Array(Box::new(item)),
            default: None,
        })
    }

    fn inferred(&self, raw: &Map<String, Value>) -> Result<Schema, String> {
        if let Some(value) = raw.get("const")
            && let Some(kind) = ScalarKind::of(value)
        {
            return Ok(scalar(kind));
        }
        if let Some(value) = raw
            .get("enum")
            .and_then(Value::as_array)
            .and_then(|values| values.iter().find(|value| !value.is_null()))
            && let Some(kind) = ScalarKind::of(value)
        {
            return Ok(scalar(kind));
        }
        Err("fact table schema node has no supported type".to_string())
    }

    fn merge(&self, variants: Vec<Schema>) -> Result<Schema, String> {
        let mut concrete = concrete_variants(variants);
        if concrete.len() == 1 {
            return Ok(concrete.remove(0));
        }
        if object_variants(&concrete) {
            return self.merge_objects(concrete);
        }
        if one_scalar_kind(&concrete) {
            return Ok(concrete.remove(0));
        }
        Ok(Schema {
            shape: Shape::Union(concrete),
            default: None,
        })
    }

    fn merge_fields(
        &self,
        fields: BTreeMap<String, Vec<Schema>>,
    ) -> Result<BTreeMap<String, Schema>, String> {
        fields
            .into_iter()
            .map(|(name, variants)| Ok((name, self.merge(variants)?)))
            .collect()
    }

    fn merge_objects(&self, concrete: Vec<Schema>) -> Result<Schema, String> {
        let (fields, required) = object_parts(concrete);
        Ok(Schema {
            shape: Shape::Object(ObjectSchema {
                fields: self.merge_fields(fields)?,
                required: required.unwrap_or_default(),
            }),
            default: None,
        })
    }

    fn object(&self, raw: &Map<String, Value>) -> Result<Schema, String> {
        if let Some(values) = additional_values(raw) {
            return Ok(Schema {
                shape: Shape::Map(Box::new(self.compile(values)?)),
                default: None,
            });
        }
        Ok(Schema {
            shape: Shape::Object(ObjectSchema {
                fields: self.object_fields(raw)?,
                required: required_fields(raw),
            }),
            default: None,
        })
    }

    fn object_fields(&self, raw: &Map<String, Value>) -> Result<BTreeMap<String, Schema>, String> {
        raw.get("properties")
            .and_then(Value::as_object)
            .into_iter()
            .flat_map(Map::iter)
            .map(|(name, field)| Ok((name.clone(), self.compile(field)?)))
            .collect()
    }

    fn reference(&self, reference: &str) -> Result<Schema, String> {
        if !self.resolving.borrow_mut().insert(reference.to_string()) {
            return Err(format!(
                "recursive fact table schema reference {reference} needs a specialized relation"
            ));
        }
        let target = self
            .root
            .pointer(reference.strip_prefix('#').unwrap_or(reference))
            .ok_or_else(|| format!("fact table schema reference {reference} is missing"))?;
        let compiled = self.compile(target);
        self.resolving.borrow_mut().remove(reference);
        compiled
    }

    fn typed(&self, raw: &Map<String, Value>) -> Result<Schema, String> {
        Ok(match raw.get("type").and_then(Value::as_str) {
            Some("array") => self.array(raw)?,
            Some("boolean") => scalar(ScalarKind::Boolean),
            Some("integer") => scalar(ScalarKind::Integer),
            Some("null") => null_schema(),
            Some("number") => scalar(ScalarKind::Float),
            Some("object") => self.object(raw)?,
            Some("string") => scalar(ScalarKind::String),
            Some(other) => return Err(format!("unsupported fact table schema type {other}")),
            None => self.inferred(raw)?,
        })
    }

    fn union(&self, variants: &[Value]) -> Result<Schema, String> {
        self.merge(
            variants
                .iter()
                .map(|variant| self.compile(variant))
                .collect::<Result<Vec<_>, _>>()?,
        )
    }
}

fn additional_values(raw: &Map<String, Value>) -> Option<&Value> {
    raw.get("properties").is_none().then_some(())?;
    raw.get("additionalProperties")
        .filter(|value| value.is_object())
}

fn concrete_variants(variants: Vec<Schema>) -> Vec<Schema> {
    variants
        .into_iter()
        .filter(|variant| !matches!(variant.shape, Shape::Null))
        .collect()
}

fn null_schema() -> Schema {
    Schema {
        shape: Shape::Null,
        default: None,
    }
}

fn object_parts(
    concrete: Vec<Schema>,
) -> (BTreeMap<String, Vec<Schema>>, Option<BTreeSet<String>>) {
    let mut fields = BTreeMap::new();
    let mut required = None;
    for variant in concrete {
        let Shape::Object(object) = variant.shape else {
            unreachable!("object variants were checked")
        };
        for (name, field) in object.fields {
            fields.entry(name).or_insert_with(Vec::new).push(field);
        }
        required = Some(intersect_required(required, object.required));
    }
    (fields, required)
}

fn intersect_required(
    held: Option<BTreeSet<String>>,
    stated: BTreeSet<String>,
) -> BTreeSet<String> {
    held.map_or(stated.clone(), |required| {
        required.intersection(&stated).cloned().collect()
    })
}

fn object_variants(concrete: &[Schema]) -> bool {
    concrete
        .iter()
        .all(|variant| matches!(variant.shape, Shape::Object(_)))
}

fn one_scalar_kind(concrete: &[Schema]) -> bool {
    let kinds = concrete
        .iter()
        .filter_map(|variant| match variant.shape {
            Shape::Scalar(kind) => Some(kind),
            _ => None,
        })
        .collect::<BTreeSet<_>>();
    kinds.len() == 1 && kinds.len() == concrete.len()
}

fn required_fields(raw: &Map<String, Value>) -> BTreeSet<String> {
    raw.get("required")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(Value::as_str)
        .map(str::to_string)
        .collect()
}
