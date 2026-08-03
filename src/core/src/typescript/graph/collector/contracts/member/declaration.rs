use crate::graph::NodeKind;
use oxc_ast::ast::{PropertyKey, TSAccessibility, TSTypeAnnotation};
use oxc_span::Span;

pub(in crate::typescript::graph::collector) struct KeyedMember<'part, 'ast> {
    pub(in crate::typescript::graph::collector) key: &'part PropertyKey<'ast>,
    pub(in crate::typescript::graph::collector) kind: NodeKind,
    pub(in crate::typescript::graph::collector) span: Span,
    pub(in crate::typescript::graph::collector) accessibility: Option<TSAccessibility>,
    pub(in crate::typescript::graph::collector) annotation: Option<&'part TSTypeAnnotation<'ast>>,
}
