use crate::calls::CallRecord;
use crate::classes::ClassRecord;
use crate::families::{AttributeAccessRecord, StringExpressionRecord};
use crate::functions::FunctionRecord;
use crate::imports::ImportBindingRecord;
use crate::syntax::SyntaxRecord;

pub(in crate::bindings::session) struct SelectedFacts {
    pub(in crate::bindings::session) functions: Option<Vec<FunctionRecord>>,
    pub(in crate::bindings::session) calls: Option<Vec<CallRecord>>,
    pub(in crate::bindings::session) classes: Option<Vec<ClassRecord>>,
    pub(in crate::bindings::session) import_bindings: Option<Vec<ImportBindingRecord>>,
    pub(in crate::bindings::session) syntax: Option<Vec<SyntaxRecord>>,
    pub(in crate::bindings::session) attribute_accesses: Option<Vec<AttributeAccessRecord>>,
    pub(in crate::bindings::session) string_expressions: Option<Vec<StringExpressionRecord>>,
}
