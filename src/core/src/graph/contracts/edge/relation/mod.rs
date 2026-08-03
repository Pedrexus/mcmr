use crate::graph::contracts::edge_kind::EdgeKind;

#[derive(Clone, Copy)]
pub struct Relation<'edge> {
    pub source: &'edge str,
    pub target: &'edge str,
    pub kind: EdgeKind,
}
