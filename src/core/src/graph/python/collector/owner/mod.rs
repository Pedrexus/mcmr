use crate::graph::contracts::NodeKind;

pub(super) struct Owner {
    pub(super) id: String,
    pub(super) kind: NodeKind,
    pub(super) qualname: String,
}
