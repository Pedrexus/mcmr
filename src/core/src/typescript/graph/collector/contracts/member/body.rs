use oxc_ast::ast::{Expression, TSTypeAnnotation};

pub(in crate::typescript::graph::collector) struct MemberBody<'part, 'ast> {
    pub(in crate::typescript::graph::collector) annotation: Option<&'part TSTypeAnnotation<'ast>>,
    pub(in crate::typescript::graph::collector) value: Option<&'part Expression<'ast>>,
}
