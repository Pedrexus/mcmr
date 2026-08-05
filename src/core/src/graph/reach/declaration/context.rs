use crate::protocol::Span;
use serde::Serialize;

#[derive(Debug, Serialize)]
pub(crate) struct DeclarationContext {
    pub(crate) span: Span,
    pub(crate) is_module_scope: bool,
    pub(crate) is_decorated: bool,
}
