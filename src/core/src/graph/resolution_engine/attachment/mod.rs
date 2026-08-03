use crate::graph::contracts::{EdgeKind, Reference};
use std::collections::BTreeSet;

pub(crate) struct Attachment<'a> {
    pub(crate) reference: &'a Reference,
    pub(crate) candidates: &'a [String],
    pub(crate) symbols: &'a BTreeSet<String>,
    pub(crate) relation_kind: EdgeKind,
}
