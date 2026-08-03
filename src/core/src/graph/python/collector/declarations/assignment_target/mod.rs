use crate::graph::contracts::NodeKind;

pub(super) struct AssignmentTarget {
    pub(super) kind: NodeKind,
    pub(super) holder: String,
    pub(super) name: String,
}
