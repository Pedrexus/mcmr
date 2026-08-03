use crate::graph::EdgeKind;
use oxc_span::Span;

pub(in crate::typescript::graph::collector) struct WrittenReference<'reference> {
    pub(in crate::typescript::graph::collector) source: &'reference str,
    pub(in crate::typescript::graph::collector) expression: &'reference str,
    pub(in crate::typescript::graph::collector) kind: EdgeKind,
    pub(in crate::typescript::graph::collector) span: Span,
}
