use crate::calls::CallRecord;
use crate::families::{AttributeAccessRecord, StringExpressionRecord};
use crate::functions::FunctionRecord;

/// Typed provider streams one frontend may fill beside compatibility JSON.
#[derive(Default)]
pub(crate) struct RecordTargets<'record> {
    pub(crate) functions: Option<&'record mut Vec<FunctionRecord>>,
    pub(crate) calls: Option<&'record mut Vec<CallRecord>>,
    pub(crate) attribute_accesses: Option<&'record mut Vec<AttributeAccessRecord>>,
    pub(crate) string_expressions: Option<&'record mut Vec<StringExpressionRecord>>,
}
