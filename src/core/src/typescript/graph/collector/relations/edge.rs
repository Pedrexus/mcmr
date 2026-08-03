use crate::graph::EdgeKind;
use oxc_span::Span;

pub(in crate::typescript::graph::collector) struct ExactEdge<'edge> {
    pub(in crate::typescript::graph::collector) source: &'edge str,
    pub(in crate::typescript::graph::collector) target: &'edge str,
    pub(in crate::typescript::graph::collector) kind: EdgeKind,
    pub(in crate::typescript::graph::collector) span: Span,
}
