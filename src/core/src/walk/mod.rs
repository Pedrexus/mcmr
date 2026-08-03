use ruff_python_ast::{Expr, Stmt};
use ruff_text_size::Ranged;

mod expressions;
mod fields;
mod traversal;

pub use expressions::{children, expression_tree, expressions};
pub use fields::{annotation_name, class_instance_fields};
pub use traversal::{blocks, statements, walk};

pub fn qualified_name(expression: &Expr) -> String {
    match expression {
        Expr::Name(name) => name.id.to_string(),
        Expr::Attribute(attribute) => {
            let base = qualified_name(&attribute.value);
            if base.is_empty() {
                String::new()
            } else {
                format!("{base}.{}", attribute.attr)
            }
        }
        Expr::Call(call) => qualified_name(&call.func),
        _ => String::new(),
    }
}

pub fn docstring(body: &[Stmt]) -> Option<String> {
    match body.first() {
        Some(Stmt::Expr(item)) => match item.value.as_ref() {
            Expr::StringLiteral(literal) => {
                let raw = literal.value.to_str();
                let (summary, body) = raw.split_once('\n').unwrap_or((raw, ""));
                let body = textwrap::dedent(body);
                let body = body.trim_matches('\n');
                Some(match body.is_empty() {
                    true => summary.trim().to_string(),
                    false => format!("{}\n\n{body}", summary.trim()),
                })
            }
            _ => None,
        },
        _ => None,
    }
}

/// Return the range one statement block covers, from its first statement to its last.
pub fn body_range(body: &[Stmt]) -> ruff_text_size::TextRange {
    match (body.first(), body.last()) {
        (Some(first), Some(last)) => {
            ruff_text_size::TextRange::new(first.range().start(), last.range().end())
        }
        _ => ruff_text_size::TextRange::default(),
    }
}

pub fn declared_name(statement: &Stmt) -> Option<String> {
    match statement {
        Stmt::ClassDef(item) => Some(item.name.to_string()),
        Stmt::FunctionDef(item) => Some(item.name.to_string()),
        _ => None,
    }
}
