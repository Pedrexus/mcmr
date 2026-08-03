use crate::{calls, classes, families, functions, imports, syntax};

#[derive(Default)]
pub struct SessionFacts {
    pub functions: Vec<functions::FunctionRecord>,
    pub calls: Vec<calls::CallRecord>,
    pub classes: Vec<classes::ClassRecord>,
    pub import_bindings: Vec<imports::ImportBindingRecord>,
    pub syntax: Vec<syntax::SyntaxRecord>,
    pub attribute_accesses: Vec<families::AttributeAccessRecord>,
    pub string_expressions: Vec<families::StringExpressionRecord>,
}
