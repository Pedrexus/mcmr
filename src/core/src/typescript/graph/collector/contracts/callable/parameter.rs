use crate::graph::ParameterKind;
use oxc_ast::ast::{FormalParameter, FormalParameterRest, TSTypeAnnotation};
use oxc_span::Span;

pub(in crate::typescript::graph::collector) struct DeclaredParameter<'part, 'ast> {
    pub(in crate::typescript::graph::collector) name: Option<String>,
    pub(in crate::typescript::graph::collector) kind: ParameterKind,
    pub(in crate::typescript::graph::collector) optional: bool,
    pub(in crate::typescript::graph::collector) annotation: Option<&'part TSTypeAnnotation<'ast>>,
    pub(in crate::typescript::graph::collector) span: Span,
}

impl<'part, 'ast> DeclaredParameter<'part, 'ast> {
    pub(in crate::typescript::graph::collector) fn ordinary(
        parameter: &'part FormalParameter<'ast>,
    ) -> Self {
        Self {
            name: parameter.pattern.get_identifier_name().map(String::from),
            kind: ParameterKind::PositionalOnly,
            optional: parameter.initializer.is_some() || parameter.optional,
            annotation: parameter.type_annotation.as_deref(),
            span: parameter.span,
        }
    }

    pub(in crate::typescript::graph::collector) fn rest(
        parameter: &'part FormalParameterRest<'ast>,
    ) -> Self {
        Self {
            name: parameter
                .rest
                .argument
                .get_identifier_name()
                .map(String::from),
            kind: ParameterKind::VarPositional,
            optional: false,
            annotation: parameter.type_annotation.as_deref(),
            span: parameter.span,
        }
    }
}
