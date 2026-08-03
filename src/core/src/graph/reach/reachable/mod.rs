use super::kind::DeclarationKind;
use crate::graph::contracts::{Language, Node};

#[derive(Clone, Copy)]
pub(super) struct Reachable<'a> {
    pub(super) node: &'a Node,
    pub(super) path: &'a str,
    pub(super) language: Language,
    pub(super) kind: DeclarationKind,
}
