use crate::protocol::Span;

pub(crate) struct NamedDefinition {
    pub(crate) name: String,
    pub(crate) span: Span,
}
