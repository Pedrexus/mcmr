use crate::bindings::relations::{NestedRow, nested_rows};
use crate::calls::{CallRecord, CallSite};

impl<'a> NestedRow<'a, CallSite> {
    pub(super) fn call(&self) -> &'a CallSite {
        self.value
    }
}

pub(super) fn call_rows(records: &[CallRecord]) -> Vec<NestedRow<'_, CallSite>> {
    nested_rows(
        records,
        "call",
        |record| record.key.as_str(),
        |record| &record.calls,
    )
}
