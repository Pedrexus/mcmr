use super::model::SyntaxDraft;
use crate::source::Source;
use oxc_ast::ast::{Expression, FunctionBody};
use oxc_span::Span;
use serde_json::Value;

mod classify;
mod visitor;

pub(super) fn callable_initializer<'a, 'ast>(
    variable: &'a oxc_ast::ast::VariableDeclarator<'ast>,
) -> Option<(Span, Option<&'a FunctionBody<'ast>>)> {
    match &variable.init {
        Some(Expression::ArrowFunctionExpression(function)) => {
            Some((variable.span, Some(function.body.as_ref())))
        }
        Some(Expression::FunctionExpression(function)) => {
            Some((variable.span, function.body.as_deref()))
        }
        _ => None,
    }
}

/// Reduce an Oxc tree to the vocabulary every language-neutral syntax rule reads.
pub(super) struct SyntaxTree {
    frames: Vec<Option<SyntaxDraft>>,
    roots: Vec<SyntaxDraft>,
}

impl SyntaxTree {
    pub(super) fn new() -> Self {
        Self {
            frames: Vec::new(),
            roots: Vec::new(),
        }
    }

    pub(super) fn values(self, source: &Source) -> Vec<Value> {
        self.roots
            .into_iter()
            .map(|node| node.value(source))
            .collect()
    }
}
