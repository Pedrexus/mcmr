use crate::source::Source;
use crate::walk::{children, docstring, expressions, walk};
use ruff_python_ast::{Expr, ExprStringLiteral, ModModule, Number, Operator};
use ruff_text_size::Ranged;

mod expression;
mod record;

pub use expression::StringExpression;
pub use record::StringExpressionRecord;

/// Build every string expression one file folds together without an intermediate JSON tree.
pub fn strings(source: &Source, module: &ModModule) -> StringExpressionRecord {
    let mut expressions_found = Vec::new();
    for statement in walk(module) {
        if docstring(std::slice::from_ref(statement)).is_some() {
            continue;
        }
        for expression in expressions(statement) {
            collect_strings(source, expression, &mut expressions_found);
        }
    }
    StringExpressionRecord {
        key: format!("stringexpressionfact:{}", source.relative),
        span: source.span(module.range()),
        language: "python".to_string(),
        expressions: expressions_found,
    }
}

fn collect_strings(source: &Source, expression: &Expr, found: &mut Vec<StringExpression>) {
    if let Some((literal, count)) = fixed_repetition(expression) {
        let value = literal.value.to_str().to_string();
        found.push(StringExpression::FixedRepetition {
            node: source.node_of("string-repetition", expression),
            literal: value,
            repetition_count: count,
        });
        return;
    }
    if let Expr::StringLiteral(item) = expression {
        let value = item.value.to_str().to_string();
        let literal_fragment_count = item.value.as_slice().len();
        assert!(
            literal_fragment_count > 0,
            "a parsed string literal must hold at least one fragment"
        );
        found.push(StringExpression::Literal {
            node: source.node_of("string", item),
            runtime_value: value.clone(),
            literal_fragment_count,
            wraps_single_runtime_line: !value.contains('\n'),
        });
    }
    for child in children(expression) {
        collect_strings(source, child, found);
    }
}

/// Return the literal and fixed count one multiplication repeats, whichever operand order it uses.
fn fixed_repetition(expression: &Expr) -> Option<(&ExprStringLiteral, usize)> {
    let Expr::BinOp(operation) = expression else {
        return None;
    };
    if operation.op != Operator::Mult {
        return None;
    }
    let (literal, count) = match (operation.left.as_ref(), operation.right.as_ref()) {
        (Expr::StringLiteral(literal), Expr::NumberLiteral(count))
        | (Expr::NumberLiteral(count), Expr::StringLiteral(literal)) => (literal, count),
        _ => return None,
    };
    match &count.value {
        Number::Int(count) if !literal.value.is_empty() => {
            count.as_usize().map(|count| (literal, count))
        }
        _ => None,
    }
}
