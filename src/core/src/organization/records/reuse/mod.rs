use super::definition::Definition;
use crate::protocol::Span;

pub(crate) struct Reuse {
    pub(crate) definition: Definition,
    pub(crate) importer_spans: Vec<Span>,
}
