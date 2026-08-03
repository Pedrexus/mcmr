use crate::{calls, classes, families, functions, imports, syntax};

/// Typed rows extracted from one source document.
#[derive(Default)]
pub(in crate::pipeline::documents) struct ExtractedRows {
    pub(in crate::pipeline::documents) functions: Vec<functions::FunctionRecord>,
    pub(in crate::pipeline::documents) calls: Vec<calls::CallRecord>,
    pub(in crate::pipeline::documents) classes: Vec<classes::ClassRecord>,
    pub(in crate::pipeline::documents) import_bindings: Vec<imports::ImportBindingRecord>,
    pub(in crate::pipeline::documents) syntax: Vec<syntax::SyntaxRecord>,
    pub(in crate::pipeline::documents) attribute_accesses: Vec<families::AttributeAccessRecord>,
    pub(in crate::pipeline::documents) string_expressions: Vec<families::StringExpressionRecord>,
}
