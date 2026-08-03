use super::kind::TypeEscapeKind;
use oxc_ast::ast::{TSAnyKeyword, TSAsExpression, TSNonNullExpression, TSTypeAssertion};
use oxc_ast_visit::Visit;
use oxc_ast_visit::walk::{
    walk_ts_as_expression, walk_ts_non_null_expression, walk_ts_type_assertion,
};
use oxc_span::Span;

/// Every place one module steps around its own types, collected as the walk meets them.
#[derive(Default)]
pub(super) struct Hatches {
    pub(super) found: Vec<(TypeEscapeKind, Span)>,
}

impl<'ast> Visit<'ast> for Hatches {
    fn visit_ts_any_keyword(&mut self, held: &TSAnyKeyword) {
        self.found.push((TypeEscapeKind::Any, held.span));
    }

    /// `x as T` asserts, and `x as const` does not, since a literal widening to itself proves
    /// nothing away and is how this language spells an immutable literal at all.
    fn visit_ts_as_expression(&mut self, held: &TSAsExpression<'ast>) {
        if !held.type_annotation.is_const_type_reference() {
            self.found.push((TypeEscapeKind::Assertion, held.span));
        }
        walk_ts_as_expression(self, held);
    }

    fn visit_ts_non_null_expression(&mut self, held: &TSNonNullExpression<'ast>) {
        self.found.push((TypeEscapeKind::NonNull, held.span));
        walk_ts_non_null_expression(self, held);
    }

    fn visit_ts_type_assertion(&mut self, held: &TSTypeAssertion<'ast>) {
        self.found.push((TypeEscapeKind::Assertion, held.span));
        walk_ts_type_assertion(self, held);
    }
}
