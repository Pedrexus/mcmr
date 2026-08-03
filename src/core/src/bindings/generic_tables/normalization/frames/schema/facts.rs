use crate::bindings::generic_tables::normalization::support::ColumnCatalog;
use crate::bindings::generic_tables::schema::{ObjectSchema, ScalarKind, Schema, Shape};

pub(crate) fn collect_fact_columns(schema: &Schema, prefix: &str, catalog: &mut ColumnCatalog) {
    if let Shape::Object(object) = &schema.shape {
        for (name, field) in &object.fields {
            if prefix.is_empty() && matches!(name.as_str(), "key" | "span" | "language") {
                continue;
            }
            let path = joined([prefix, name]);
            collect_row_columns(field, &path, catalog);
        }
    }
}

pub(super) fn collect_row_columns(schema: &Schema, path: &str, catalog: &mut ColumnCatalog) {
    match &schema.shape {
        Shape::Scalar(kind) => catalog.insert(path.to_string(), *kind),
        Shape::Union(variants) => collect_row_variants(variants, path, catalog),
        Shape::Object(object) => collect_object_columns(object, path, catalog),
        Shape::Array(_) | Shape::Map(_) => collect_container_columns(path, catalog),
        Shape::Null => {}
    }
}

fn collect_container_columns(path: &str, catalog: &mut ColumnCatalog) {
    catalog.insert(format!("{path}.present"), ScalarKind::Boolean);
    catalog.insert(format!("{path}.length"), ScalarKind::Integer);
}

fn collect_object_columns(object: &ObjectSchema, path: &str, catalog: &mut ColumnCatalog) {
    for (name, field) in &object.fields {
        collect_row_columns(field, &joined([path, name]), catalog);
    }
}

fn collect_row_variants(variants: &[Schema], path: &str, catalog: &mut ColumnCatalog) {
    for variant in variants {
        collect_row_columns(variant, path, catalog);
    }
}

pub(crate) fn joined([prefix, name]: [&str; 2]) -> String {
    if prefix.is_empty() {
        name.to_string()
    } else {
        format!("{prefix}.{name}")
    }
}
