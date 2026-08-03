use super::{SyntaxTree, classify};
use oxc_ast::ast::{Class, Function};
use oxc_ast::ast_kind::AstKind;
use oxc_ast_visit::Visit;
use oxc_syntax::scope::ScopeFlags;

impl<'ast> Visit<'ast> for SyntaxTree {
    fn enter_node(&mut self, kind: AstKind<'ast>) {
        self.frames.push(classify::draft(kind));
    }

    fn leave_node(&mut self, _kind: AstKind<'ast>) {
        let Some(Some(node)) = self.frames.pop() else {
            return;
        };
        if let Some(parent) = self.frames.iter_mut().rev().find_map(Option::as_mut) {
            parent.children.push(node);
        } else {
            self.roots.push(node);
        }
    }

    /// A bound arrow function carries its own fact and cannot count against its owner.
    fn visit_arrow_function_expression(
        &mut self,
        _function: &oxc_ast::ast::ArrowFunctionExpression<'ast>,
    ) {
    }

    /// A nested class contributes declarations of its own and no body to its owner.
    fn visit_class(&mut self, _class: &Class<'ast>) {}

    /// A nested function carries its own fact and cannot count against its owner.
    fn visit_function(&mut self, _function: &Function<'ast>, _flags: ScopeFlags) {}
}
