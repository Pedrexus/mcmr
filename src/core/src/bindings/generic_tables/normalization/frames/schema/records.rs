use super::facts::collect_row_columns;
use crate::bindings::generic_tables::normalization::support::ColumnCatalog;
use crate::bindings::generic_tables::schema::{ObjectSchema, Schema, Shape};

pub(crate) fn collect_record_columns(schema: &Schema, catalog: &mut ColumnCatalog) {
    match &schema.shape {
        Shape::Array(item) => collect_array_records(item, catalog),
        Shape::Map(item) => collect_record_columns(item, catalog),
        Shape::Object(object) => collect_object_records(object, catalog),
        Shape::Union(variants) => collect_record_variants(variants, catalog),
        Shape::Null | Shape::Scalar(_) => {}
    }
}

fn collect_array_records(item: &Schema, catalog: &mut ColumnCatalog) {
    if matches!(item.shape, Shape::Object(_)) {
        collect_row_columns(item, "", catalog);
    }
    collect_record_columns(item, catalog);
}

fn collect_object_records(object: &ObjectSchema, catalog: &mut ColumnCatalog) {
    for field in object.fields.values() {
        collect_record_columns(field, catalog);
    }
}

fn collect_record_variants(variants: &[Schema], catalog: &mut ColumnCatalog) {
    for variant in variants {
        collect_record_columns(variant, catalog);
    }
}
