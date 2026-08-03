use super::identity::Identity;
use crate::protocol::Span;

#[derive(Clone)]
pub(crate) struct Definition {
    pub(crate) identity: Identity,
    pub(crate) path: String,
    pub(crate) is_test: bool,
    pub(crate) span: Option<Span>,
}
