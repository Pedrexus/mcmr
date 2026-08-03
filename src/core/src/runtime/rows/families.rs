use crate::{calls, classes, families, functions, imports, syntax};

/// Typed row destinations selected for one analysis.
#[derive(Default)]
pub(crate) struct TypedFamilies<'a> {
    pub(crate) functions: Option<&'a mut Vec<functions::FunctionRecord>>,
    pub(crate) calls: Option<&'a mut Vec<calls::CallRecord>>,
    pub(crate) classes: Option<&'a mut Vec<classes::ClassRecord>>,
    pub(crate) import_bindings: Option<&'a mut Vec<imports::ImportBindingRecord>>,
    pub(crate) syntax: Option<&'a mut Vec<syntax::SyntaxRecord>>,
    pub(crate) attribute_accesses: Option<&'a mut Vec<families::AttributeAccessRecord>>,
    pub(crate) string_expressions: Option<&'a mut Vec<families::StringExpressionRecord>>,
}
