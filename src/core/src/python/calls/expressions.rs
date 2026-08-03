use crate::calls::{Expression as CallExpression, MappingEntry};
use crate::source::Source;
use crate::walk::qualified_name;
use ruff_python_ast::Expr;
use ruff_text_size::Ranged;

pub(super) fn argument_value(source: &Source, expression: &Expr) -> CallExpression {
    let mut value = CallExpression::new(
        source.slice(expression.range()).to_string(),
        source.node_of("expression", expression),
    );
    value.qualified_name = match expression {
        Expr::Call(call) => qualified_name(&call.func),
        _ => String::new(),
    };
    value.literal_kind = literal_kind(expression).to_string();
    value.resolved_type = if bool_expression(expression) {
        "bool".to_string()
    } else {
        String::new()
    };
    value.arguments = call_arguments(source, expression);
    value.entries = mapping_entries(source, expression);
    value
}

fn call_arguments(source: &Source, expression: &Expr) -> Vec<CallExpression> {
    match expression {
        Expr::Call(call) => call
            .arguments
            .args
            .iter()
            .map(|argument| argument_value(source, argument))
            .collect(),
        _ => Vec::new(),
    }
}

fn mapping_entries(source: &Source, expression: &Expr) -> Vec<MappingEntry<CallExpression>> {
    match expression {
        Expr::Dict(dict) => dict
            .items
            .iter()
            .filter_map(|item| {
                item.key.as_ref().map(|key| MappingEntry {
                    key: source
                        .slice(key.range())
                        .trim_matches(['"', '\''])
                        .to_string(),
                    value: argument_value(source, &item.value),
                })
            })
            .collect(),
        _ => Vec::new(),
    }
}

fn literal_kind(expression: &Expr) -> &'static str {
    match expression {
        Expr::StringLiteral(_) => "string",
        Expr::NumberLiteral(_) => "number",
        Expr::BooleanLiteral(_) => "boolean",
        Expr::Dict(_) => "mapping",
        Expr::List(_) | Expr::Tuple(_) | Expr::Set(_) => "sequence",
        _ => "none",
    }
}

/// Whether syntax alone proves that an expression evaluates to the exact Boolean type.
fn bool_expression(expression: &Expr) -> bool {
    match expression {
        Expr::BooleanLiteral(_) | Expr::Compare(_) => true,
        Expr::UnaryOp(item) => item.op == ruff_python_ast::UnaryOp::Not,
        Expr::BoolOp(item) => item.values.iter().all(bool_expression),
        Expr::If(item) => bool_expression(&item.body) && bool_expression(&item.orelse),
        _ => false,
    }
}
