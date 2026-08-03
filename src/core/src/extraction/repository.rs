use crate::{discovery, protocol::Request};

#[derive(Clone, Copy)]
pub(crate) struct RepositoryExtraction<'a> {
    pub(crate) request: &'a Request,
    pub(crate) built: &'a [String],
    pub(crate) inventory: &'a discovery::Inventory,
}
