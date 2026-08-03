use oxc_ast::ast::{
    ArrowFunctionExpression, FormalParameters, Function, FunctionBody, MethodDefinition,
    TSMethodSignature, TSTypeAnnotation, TSTypeParameterDeclaration,
};

pub(in crate::typescript::graph::collector) struct CallableSignature<'part, 'ast> {
    pub(in crate::typescript::graph::collector) generics:
        Option<&'part TSTypeParameterDeclaration<'ast>>,
    pub(in crate::typescript::graph::collector) parameters: &'part FormalParameters<'ast>,
    pub(in crate::typescript::graph::collector) returns: Option<&'part TSTypeAnnotation<'ast>>,
    pub(in crate::typescript::graph::collector) body: Option<&'part FunctionBody<'ast>>,
}

impl<'part, 'ast> CallableSignature<'part, 'ast> {
    pub(in crate::typescript::graph::collector) fn from_arrow(
        arrow: &'part ArrowFunctionExpression<'ast>,
    ) -> Self {
        Self {
            generics: arrow.type_parameters.as_deref(),
            parameters: &arrow.params,
            returns: arrow.return_type.as_deref(),
            body: Some(&arrow.body),
        }
    }

    pub(in crate::typescript::graph::collector) fn from_function(
        function: &'part Function<'ast>,
    ) -> Self {
        Self {
            generics: function.type_parameters.as_deref(),
            parameters: &function.params,
            returns: function.return_type.as_deref(),
            body: function.body.as_deref(),
        }
    }

    pub(in crate::typescript::graph::collector) fn from_method(
        method: &'part MethodDefinition<'ast>,
    ) -> Self {
        Self {
            generics: method.value.type_parameters.as_deref(),
            parameters: &method.value.params,
            returns: method.value.return_type.as_deref(),
            body: method.value.body.as_deref(),
        }
    }

    pub(in crate::typescript::graph::collector) fn from_signature(
        signature: &'part TSMethodSignature<'ast>,
    ) -> Self {
        Self {
            generics: signature.type_parameters.as_deref(),
            parameters: &signature.params,
            returns: signature.return_type.as_deref(),
            body: None,
        }
    }
}
