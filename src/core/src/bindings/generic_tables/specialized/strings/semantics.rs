use crate::families::StringExpression;
use crate::protocol::Node;

pub(super) fn string_node(expression: &StringExpression) -> &Node {
    match expression {
        StringExpression::Literal { node, .. }
        | StringExpression::FixedRepetition { node, .. } => node,
    }
}

pub(super) fn string_kind(expression: &StringExpression) -> &'static str {
    match expression {
        StringExpression::Literal { .. } => "literal",
        StringExpression::FixedRepetition { .. } => "fixed-repetition",
    }
}

pub(super) fn repeated_literal(expression: &StringExpression) -> Option<&str> {
    match expression {
        StringExpression::Literal { .. } => None,
        StringExpression::FixedRepetition { literal, .. } => Some(literal),
    }
}

pub(super) fn literal_fragments(expression: &StringExpression) -> i64 {
    match expression {
        StringExpression::Literal {
            literal_fragment_count,
            ..
        } => *literal_fragment_count as i64,
        StringExpression::FixedRepetition { .. } => 1,
    }
}

pub(super) fn repetitions(expression: &StringExpression) -> i64 {
    match expression {
        StringExpression::Literal { .. } => 0,
        StringExpression::FixedRepetition {
            repetition_count, ..
        } => *repetition_count as i64,
    }
}

pub(super) fn runtime_value(expression: &StringExpression) -> Option<&str> {
    match expression {
        StringExpression::Literal { runtime_value, .. } => Some(runtime_value),
        StringExpression::FixedRepetition { .. } => None,
    }
}

pub(super) fn wraps_single_line(expression: &StringExpression) -> bool {
    match expression {
        StringExpression::Literal {
            wraps_single_runtime_line,
            ..
        } => *wraps_single_runtime_line,
        StringExpression::FixedRepetition { .. } => false,
    }
}
