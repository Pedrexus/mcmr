use super::place::ExpressionPlace;
use crate::calls::Expression;

pub(in crate::bindings::tables::calls::expressions) struct ExpressionRow<'record> {
    pub(in crate::bindings::tables::calls::expressions) id: String,
    pub(in crate::bindings::tables::calls::expressions) call_id: String,
    pub(in crate::bindings::tables::calls::expressions) place: ExpressionPlace,
    pub(in crate::bindings::tables::calls::expressions) expression: &'record Expression,
}
