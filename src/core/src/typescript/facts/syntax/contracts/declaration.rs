use super::name::QualifiedName;
use crate::source::Source;
use crate::typescript::facts::syntax::model::{SyntaxNode, SyntaxSemantic};
use crate::typescript::facts::syntax::tree::SyntaxTree;
use crate::typescript::support::range;
use oxc_ast::ast::FunctionBody;
use oxc_ast_visit::Visit;
use oxc_span::Span;
use serde_json::Value;

pub(in crate::typescript::facts::syntax) struct SyntaxDeclaration<'a, 'ast> {
    pub(in crate::typescript::facts::syntax) body: Option<&'a FunctionBody<'ast>>,
    pub(in crate::typescript::facts::syntax) kind: SyntaxSemantic,
    pub(in crate::typescript::facts::syntax) name: QualifiedName<'a>,
    pub(in crate::typescript::facts::syntax) span: Span,
}

impl SyntaxDeclaration<'_, '_> {
    pub(in crate::typescript::facts::syntax) fn fact(self, source: &Source) -> Value {
        let qualname = self.name.value();
        crate::syntax::fact(
            source,
            crate::syntax::SyntaxFactIdentity {
                language: "typescript",
                qualname: &qualname,
                written: source.slice(range(self.span)),
            },
            self.tree(source),
        )
    }

    fn children(&self, source: &Source) -> Vec<Value> {
        let mut builder = SyntaxTree::new();
        if let Some(body) = self.body {
            builder.visit_function_body(body);
        }
        builder.values(source)
    }

    fn tree(&self, source: &Source) -> Value {
        SyntaxNode {
            children: self.children(source),
            kind: self.kind,
            name: self.name.leaf().to_string(),
            span: self.span,
        }
        .value(source)
    }
}
