use self::entries::{EntryContext, container_entries};
use self::location::ValueLocation;
use self::nested::{NestedContainer, NestedEntry, NestedLocation};
use self::values::{
    append_container_metadata, append_scalar_field, array_entries, concise_root, container_length,
    is_root_metadata, map_entries, object_schema, scalar_value, stated_field,
};
use super::frames::joined;
use super::kind::ContainerKind;
use super::path::{FieldContext, RowPath};
use super::support::{RecordRow, ScalarKey, ScalarValue, ValueRow};
use crate::bindings::generic_tables::schema::{Schema, Shape, effective};
use serde_json::{Map, Value};
use std::collections::HashMap;

mod entries;
mod location;
mod nested;
mod values;

pub(super) struct Traversal<'fact, 'tables> {
    pub(super) fact_order: u64,
    pub(super) fact_id: &'fact str,
    pub(super) records: &'tables mut Vec<RecordRow>,
    pub(super) values: &'tables mut Vec<ValueRow>,
}

impl Traversal<'_, '_> {
    pub(super) fn normalize(
        &mut self,
        schema: &Schema,
        actual: Option<&Value>,
        path: RowPath<'_>,
        scalars: &mut HashMap<ScalarKey, ScalarValue>,
    ) -> Result<(), String> {
        let object = object_schema(schema)?;
        let actual = effective(schema, actual);
        if actual.is_none_or(Value::is_null) {
            return Ok(());
        }
        let stated = actual.and_then(Value::as_object);
        let concise_root = concise_root(actual, object, stated);
        if actual.is_some() && stated.is_none() && concise_root.is_none() {
            return Err(format!("relation {} is not an object", path.relation));
        }
        self.append_object_fields(object, stated, path, concise_root, scalars)
    }

    pub(super) fn root_scalars(
        &mut self,
        schema: &Schema,
        fact: &Value,
        parent_id: &str,
    ) -> Result<HashMap<ScalarKey, ScalarValue>, String> {
        let mut scalars = HashMap::new();
        self.normalize(
            schema,
            Some(fact),
            RowPath {
                scalar: "",
                relation: "",
                parent_id,
            },
            &mut scalars,
        )?;
        Ok(scalars)
    }

    fn append_collection_field(
        &mut self,
        context: FieldContext<'_>,
        item: &Schema,
        scalars: &mut HashMap<ScalarKey, ScalarValue>,
        kind: ContainerKind,
    ) -> Result<(), String> {
        let scalar = joined([context.path.scalar, context.name]);
        let relation = joined([context.path.relation, context.name]);
        let container = effective(context.field, context.actual);
        append_container_metadata(scalars, &scalar, container, kind)?;
        self.append_container(&relation, item, container, context.path.parent_id, kind)
    }

    fn append_container(
        &mut self,
        relation: &str,
        item: &Schema,
        actual: Option<&Value>,
        parent_id: &str,
        kind: ContainerKind,
    ) -> Result<(), String> {
        let Some(actual) = actual.filter(|value| !value.is_null()) else {
            return Ok(());
        };
        let entries = container_entries(kind, actual, relation)?;
        let length = entries.len();
        self.append_entries(relation, item, parent_id, length, entries)
    }

    fn append_entries<'value>(
        &mut self,
        relation: &str,
        item: &Schema,
        parent_id: &str,
        length: usize,
        entries: impl Iterator<Item = (Option<&'value str>, &'value Value)>,
    ) -> Result<(), String> {
        for (ordinal, (map_key, value)) in entries.enumerate() {
            self.append_entry(EntryContext {
                relation,
                item,
                parent_id,
                length,
                ordinal: ordinal as u64,
                map_key,
                value,
            })?;
        }
        Ok(())
    }

    fn append_entry(&mut self, entry: EntryContext<'_>) -> Result<(), String> {
        match &entry.item.shape {
            Shape::Object(_) if entry.map_key.is_none() => self.append_record(
                entry.relation,
                entry.item,
                entry.value,
                entry.parent_id,
                entry.ordinal,
            ),
            Shape::Scalar(_) | Shape::Union(_) => self.append_top_value(entry),
            Shape::Array(_) | Shape::Map(_) => self.append_top_container(entry),
            Shape::Object(_) => Err(format!(
                "relation {} map has non-value entries",
                entry.relation
            )),
            Shape::Null => Ok(()),
        }
    }

    fn append_field(
        &mut self,
        context: FieldContext<'_>,
        scalars: &mut HashMap<ScalarKey, ScalarValue>,
    ) -> Result<(), String> {
        match &context.field.shape {
            Shape::Scalar(_) | Shape::Union(_) => append_scalar_field(context, scalars),
            Shape::Object(_) => self.append_object_field(context, scalars),
            Shape::Array(item) => {
                self.append_collection_field(context, item, scalars, ContainerKind::Array)
            }
            Shape::Map(item) => {
                self.append_collection_field(context, item, scalars, ContainerKind::Map)
            }
            Shape::Null => Ok(()),
        }
    }

    fn append_nested_array(
        &mut self,
        relation: &str,
        item: &Schema,
        entries: &[Value],
        container: NestedContainer<'_>,
    ) -> Result<(), String> {
        for (ordinal, value) in entries.iter().enumerate() {
            self.append_nested_entry(
                relation,
                item,
                value,
                NestedEntry {
                    container_id: container.id,
                    container_ordinal: container.ordinal,
                    container_length: container.length,
                    ordinal: ordinal as u64,
                    map_key: container.map_key.clone(),
                },
            )?;
        }
        Ok(())
    }

    fn append_nested_container(
        &mut self,
        relation: &str,
        schema: &Schema,
        actual: &Value,
        location: NestedLocation<'_>,
    ) -> Result<(), String> {
        let container_id = format!(
            "{}/{relation}:container:{}",
            location.parent_id, location.container_ordinal
        );
        let length = container_length(schema, actual, relation)?;
        self.values
            .push(self.container_row(relation, &location, &container_id, length));
        self.append_nested_items(
            relation,
            schema,
            actual,
            NestedContainer::from_location(&container_id, length, location),
        )
    }

    fn append_nested_entry(
        &mut self,
        relation: &str,
        schema: &Schema,
        actual: &Value,
        entry: NestedEntry<'_>,
    ) -> Result<(), String> {
        match &schema.shape {
            Shape::Scalar(_) | Shape::Union(_) => {
                self.append_value(relation, schema, actual, ValueLocation::nested(entry))
            }
            Shape::Array(_) | Shape::Map(_) => self.append_nested_container(
                relation,
                schema,
                actual,
                NestedLocation::from_entry(entry),
            ),
            _ => Err(format!(
                "relation {relation} nested container holds records"
            )),
        }
    }

    fn append_nested_items(
        &mut self,
        relation: &str,
        schema: &Schema,
        actual: &Value,
        container: NestedContainer<'_>,
    ) -> Result<(), String> {
        match &schema.shape {
            Shape::Array(item) => {
                self.append_nested_array(relation, item, array_entries(actual), container)
            }
            Shape::Map(item) => {
                self.append_nested_map(relation, item, map_entries(actual), container)
            }
            _ => unreachable!("a nested container schema was checked before traversal"),
        }
    }

    fn append_nested_map(
        &mut self,
        relation: &str,
        item: &Schema,
        entries: &serde_json::Map<String, Value>,
        container: NestedContainer<'_>,
    ) -> Result<(), String> {
        for (ordinal, (key, value)) in entries.iter().enumerate() {
            self.append_nested_entry(
                relation,
                item,
                value,
                NestedEntry {
                    container_id: container.id,
                    container_ordinal: container.ordinal,
                    container_length: container.length,
                    ordinal: ordinal as u64,
                    map_key: Some(key.clone()),
                },
            )?;
        }
        Ok(())
    }

    fn append_object_field(
        &mut self,
        context: FieldContext<'_>,
        scalars: &mut HashMap<ScalarKey, ScalarValue>,
    ) -> Result<(), String> {
        let scalar = joined([context.path.scalar, context.name]);
        let relation = joined([context.path.relation, context.name]);
        self.normalize(
            context.field,
            context.actual,
            RowPath {
                scalar: &scalar,
                relation: &relation,
                parent_id: context.path.parent_id,
            },
            scalars,
        )
    }

    fn append_object_fields(
        &mut self,
        object: &crate::bindings::generic_tables::schema::ObjectSchema,
        stated: Option<&Map<String, Value>>,
        path: RowPath<'_>,
        concise: Option<&Value>,
        scalars: &mut HashMap<ScalarKey, ScalarValue>,
    ) -> Result<(), String> {
        for (name, field) in &object.fields {
            if is_root_metadata(path, name) {
                continue;
            }
            let context = stated_field(
                FieldContext::new(name, field, None, path),
                stated,
                object,
                concise,
            )?;
            self.append_field(context, scalars)?;
        }
        Ok(())
    }

    fn append_record(
        &mut self,
        relation: &str,
        schema: &Schema,
        actual: &Value,
        parent_id: &str,
        ordinal: u64,
    ) -> Result<(), String> {
        let record_id = format!("{parent_id}/{relation}:{ordinal}");
        let mut scalars = HashMap::new();
        self.normalize(
            schema,
            Some(actual),
            RowPath {
                scalar: "",
                relation,
                parent_id: &record_id,
            },
            &mut scalars,
        )?;
        self.records
            .push(self.record_row(relation, ordinal, parent_id, record_id, scalars));
        Ok(())
    }

    fn append_top_container(&mut self, entry: EntryContext<'_>) -> Result<(), String> {
        self.append_nested_container(
            entry.relation,
            entry.item,
            entry.value,
            NestedLocation {
                parent_id: entry.parent_id,
                container_ordinal: entry.ordinal,
                map_key: entry.map_key.map(str::to_string),
            },
        )
    }

    fn append_top_value(&mut self, entry: EntryContext<'_>) -> Result<(), String> {
        self.append_value(
            entry.relation,
            entry.item,
            entry.value,
            ValueLocation::top(
                entry.parent_id,
                entry.ordinal,
                entry.relation,
                entry.length,
                entry.map_key.map(str::to_string),
            ),
        )
    }

    fn append_value(
        &mut self,
        relation: &str,
        schema: &Schema,
        actual: &Value,
        location: ValueLocation<'_>,
    ) -> Result<(), String> {
        let value = scalar_value(schema, Some(actual))?
            .ok_or_else(|| format!("relation {relation} value is not scalar"))?;
        self.values.push(self.value_row(relation, location, value));
        Ok(())
    }

    fn container_row(
        &self,
        relation: &str,
        location: &NestedLocation<'_>,
        container_id: &str,
        length: u64,
    ) -> ValueRow {
        ValueRow {
            fact_order: self.fact_order,
            fact_id: self.fact_id.to_string(),
            location: crate::bindings::generic_tables::normalization::support::ValueLocation {
                relation: relation.to_string(),
                parent_id: location.parent_id.to_string(),
                container:
                    crate::bindings::generic_tables::normalization::support::ValueContainer {
                        id: container_id.to_string(),
                        ordinal: Some(location.container_ordinal),
                        length: Some(length),
                    },
                entry_kind: "container".to_string(),
                value_id: container_id.to_string(),
                ordinal: 0,
                map_key: location.map_key.clone(),
            },
            value: None,
        }
    }

    fn record_row(
        &self,
        relation: &str,
        ordinal: u64,
        parent_id: &str,
        record_id: String,
        scalars: HashMap<ScalarKey, ScalarValue>,
    ) -> RecordRow {
        RecordRow {
            fact_order: self.fact_order,
            fact_id: self.fact_id.to_string(),
            relation: relation.to_string(),
            parent_id: parent_id.to_string(),
            record_id,
            ordinal,
            scalars,
        }
    }

    fn value_row(
        &self,
        relation: &str,
        location: ValueLocation<'_>,
        value: ScalarValue,
    ) -> ValueRow {
        ValueRow {
            fact_order: self.fact_order,
            fact_id: self.fact_id.to_string(),
            location: crate::bindings::generic_tables::normalization::support::ValueLocation {
                relation: relation.to_string(),
                parent_id: location.parent_id.to_string(),
                container:
                    crate::bindings::generic_tables::normalization::support::ValueContainer {
                        id: location.container_id,
                        ordinal: location.container_ordinal,
                        length: Some(location.container_length),
                    },
                entry_kind: "value".to_string(),
                value_id: location.value_id,
                ordinal: location.ordinal,
                map_key: location.map_key,
            },
            value: Some(value),
        }
    }
}
