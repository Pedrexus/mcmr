use crate::graph::{NodeKind, Visibility};
use oxc_ast::ast::{ArrowFunctionExpression, Function, MethodDefinition, TSMethodSignature};
use oxc_span::Span;

pub(in crate::typescript::graph::collector) struct CallableDeclaration<'part, 'ast> {
    pub(in crate::typescript::graph::collector) name: &'part str,
    pub(in crate::typescript::graph::collector) kind: NodeKind,
    pub(in crate::typescript::graph::collector) span: Span,
    pub(in crate::typescript::graph::collector) visibility: Visibility,
    pub(in crate::typescript::graph::collector) asynchronous: bool,
    pub(in crate::typescript::graph::collector) returns:
        Option<&'part oxc_ast::ast::TSTypeAnnotation<'ast>>,
}

impl<'part, 'ast> CallableDeclaration<'part, 'ast> {
    pub(in crate::typescript::graph::collector) fn from_arrow(
        name: &'part str,
        visibility: Visibility,
        span: Span,
        arrow: &'part ArrowFunctionExpression<'ast>,
    ) -> Self {
        Self {
            name,
            kind: NodeKind::Function,
            span,
            visibility,
            asynchronous: arrow.r#async,
            returns: arrow.return_type.as_deref(),
        }
    }

    pub(in crate::typescript::graph::collector) fn from_function(
        name: &'part str,
        visibility: Visibility,
        span: Span,
        function: &'part Function<'ast>,
    ) -> Self {
        Self {
            name,
            kind: NodeKind::Function,
            span,
            visibility,
            asynchronous: function.r#async,
            returns: function.return_type.as_deref(),
        }
    }

    pub(in crate::typescript::graph::collector) fn from_method(
        name: &'part str,
        visibility: Visibility,
        method: &'part MethodDefinition<'ast>,
    ) -> Self {
        Self {
            name,
            kind: match method.kind.is_accessor() {
                true => NodeKind::Property,
                false => NodeKind::Method,
            },
            span: method.span,
            visibility,
            asynchronous: method.value.r#async,
            returns: method.value.return_type.as_deref(),
        }
    }

    pub(in crate::typescript::graph::collector) fn from_signature(
        name: &'part str,
        signature: &'part TSMethodSignature<'ast>,
    ) -> Self {
        Self {
            name,
            kind: NodeKind::Method,
            span: signature.span,
            visibility: Visibility::Public,
            asynchronous: false,
            returns: signature.return_type.as_deref(),
        }
    }
}
