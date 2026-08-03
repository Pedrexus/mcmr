use super::super::model::{SyntaxDraft, SyntaxSemantic};
use crate::typescript::support::expression_name;
use oxc_ast::ast_kind::AstKind;
use oxc_span::{GetSpan, Span};

pub(super) fn draft(kind: AstKind<'_>) -> Option<SyntaxDraft> {
    let span = kind.span();
    [
        declaration(kind, span),
        control(kind, span),
        flow(kind, span),
        invocation(kind, span),
        reference(kind, span),
        value(kind, span),
        operation(kind, span),
    ]
    .into_iter()
    .flatten()
    .next()
}

fn control(kind: AstKind<'_>, span: Span) -> Option<SyntaxDraft> {
    let semantic = match kind {
        AstKind::IfStatement(_) | AstKind::ConditionalExpression(_) => SyntaxSemantic::Branch,
        AstKind::ForStatement(_)
        | AstKind::ForInStatement(_)
        | AstKind::ForOfStatement(_)
        | AstKind::WhileStatement(_)
        | AstKind::DoWhileStatement(_) => SyntaxSemantic::Loop,
        AstKind::TryStatement(_) => SyntaxSemantic::Guard,
        AstKind::WithStatement(_) => SyntaxSemantic::Scope,
        _ => return None,
    };
    Some(SyntaxDraft::new(semantic, String::new(), span))
}

fn declaration(kind: AstKind<'_>, span: Span) -> Option<SyntaxDraft> {
    match kind {
        AstKind::VariableDeclarator(item) => Some(SyntaxDraft::new(
            SyntaxSemantic::Binding,
            item.id
                .get_identifier_name()
                .map(|name| name.to_string())
                .unwrap_or_default(),
            span,
        )),
        AstKind::ExpressionStatement(item) => Some(SyntaxDraft::new(
            SyntaxSemantic::Effect,
            String::new(),
            item.expression.span(),
        )),
        _ => None,
    }
}

fn flow(kind: AstKind<'_>, span: Span) -> Option<SyntaxDraft> {
    let (semantic, name) = match kind {
        AstKind::ReturnStatement(_) => (SyntaxSemantic::Return, String::new()),
        AstKind::ThrowStatement(_) => (SyntaxSemantic::Raise, String::new()),
        AstKind::DebuggerStatement(_) => (SyntaxSemantic::Effect, "debugger".to_string()),
        AstKind::AwaitExpression(_) => (SyntaxSemantic::Await, String::new()),
        _ => return None,
    };
    Some(SyntaxDraft::new(semantic, name, span))
}

fn invocation(kind: AstKind<'_>, span: Span) -> Option<SyntaxDraft> {
    let name = match kind {
        AstKind::CallExpression(item) => expression_name(&item.callee),
        AstKind::NewExpression(item) => expression_name(&item.callee),
        _ => return None,
    };
    Some(SyntaxDraft::new(
        SyntaxSemantic::Call,
        name.unwrap_or_default(),
        span,
    ))
}

fn operation(kind: AstKind<'_>, span: Span) -> Option<SyntaxDraft> {
    let semantic = match kind {
        AstKind::BinaryExpression(_)
        | AstKind::LogicalExpression(_)
        | AstKind::UnaryExpression(_)
        | AstKind::UpdateExpression(_) => SyntaxSemantic::Operation,
        AstKind::AssignmentExpression(_) => SyntaxSemantic::Binding,
        _ => return None,
    };
    Some(SyntaxDraft::new(semantic, String::new(), span))
}

fn reference(kind: AstKind<'_>, span: Span) -> Option<SyntaxDraft> {
    let (semantic, name) = match kind {
        AstKind::StaticMemberExpression(item) => (SyntaxSemantic::Member, static_member(item)),
        AstKind::PrivateFieldExpression(item) => (SyntaxSemantic::Member, private_member(item)),
        AstKind::IdentifierReference(item) => (SyntaxSemantic::Name, item.name.to_string()),
        AstKind::ThisExpression(_) => (SyntaxSemantic::Name, "this".to_string()),
        _ => return None,
    };
    Some(SyntaxDraft::new(semantic, name, span))
}

fn private_member(item: &oxc_ast::ast::PrivateFieldExpression<'_>) -> String {
    expression_name(&item.object)
        .map(|owner| format!("{owner}.#{}", item.field.name))
        .unwrap_or_else(|| format!("#{}", item.field.name))
}

fn static_member(item: &oxc_ast::ast::StaticMemberExpression<'_>) -> String {
    expression_name(&item.object)
        .map(|owner| format!("{owner}.{}", item.property.name))
        .unwrap_or_else(|| item.property.name.to_string())
}

fn value(kind: AstKind<'_>, span: Span) -> Option<SyntaxDraft> {
    let semantic = match kind {
        AstKind::StringLiteral(_) | AstKind::TemplateLiteral(_) => SyntaxSemantic::Text,
        AstKind::BooleanLiteral(_)
        | AstKind::NullLiteral(_)
        | AstKind::NumericLiteral(_)
        | AstKind::BigIntLiteral(_) => SyntaxSemantic::Literal,
        AstKind::ArrayExpression(_) | AstKind::ObjectExpression(_) => SyntaxSemantic::Collection,
        _ => return None,
    };
    Some(SyntaxDraft::new(semantic, String::new(), span))
}
