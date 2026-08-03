use crate::source::Source;
use oxc_ast::ast::Expression;
use oxc_span::Span;
use serde_json::{Value, json};

/// Return one oxc span as the range every extractor in this kernel measures with.
pub(super) fn range(span: Span) -> ruff_text_size::TextRange {
    ruff_text_size::TextRange::new(span.start.into(), span.end.into())
}

pub(super) fn base(source: &Source, key: &str) -> Value {
    json!({
        "key": key,
        "span": source.span(range(Span::default())),
        "language": "typescript",
    })
}

/// Return the dotted name one expression reads as, when every step of it is a plain name.
pub(super) fn expression_name(expression: &Expression<'_>) -> Option<String> {
    match expression {
        Expression::Identifier(held) => Some(held.name.to_string()),
        Expression::ThisExpression(_) => Some("this".to_string()),
        Expression::StaticMemberExpression(held) => {
            qualified_name(&held.object, &held.property.name)
        }
        Expression::PrivateFieldExpression(held) => {
            qualified_name(&held.object, &format!("#{}", held.field.name))
        }
        Expression::ParenthesizedExpression(held) => expression_name(&held.expression),
        Expression::TSNonNullExpression(held) => expression_name(&held.expression),
        Expression::TSAsExpression(held) => expression_name(&held.expression),
        _ => None,
    }
}

fn qualified_name(object: &Expression<'_>, member: &str) -> Option<String> {
    Some(format!("{}.{member}", expression_name(object)?))
}
