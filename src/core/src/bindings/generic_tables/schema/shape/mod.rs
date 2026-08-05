use super::ScalarKind;

pub(crate) use object::ObjectSchema;

mod object;

#[derive(Clone, Debug)]
pub(crate) enum Shape<Schema, Object> {
    Array(Box<Schema>),
    Map(Box<Schema>),
    Null,
    Object(Object),
    Scalar(ScalarKind),
    Union(Vec<Schema>),
}
