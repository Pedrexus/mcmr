use super::super::super::schema::Schema;
use super::row::RowPath;
use serde_json::Value;

#[derive(Clone, Copy)]
pub(crate) struct FieldContext<'a> {
    pub(crate) name: &'a str,
    pub(crate) field: &'a Schema,
    pub(crate) actual: Option<&'a Value>,
    pub(crate) path: RowPath<'a>,
}

impl<'a> FieldContext<'a> {
    pub(crate) fn new(
        name: &'a str,
        field: &'a Schema,
        actual: Option<&'a Value>,
        path: RowPath<'a>,
    ) -> Self {
        Self {
            name,
            field,
            actual,
            path,
        }
    }

    pub(crate) fn with_actual(self, actual: Option<&'a Value>) -> Self {
        Self { actual, ..self }
    }
}
