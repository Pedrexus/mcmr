use super::support::range;
use crate::functions::FunctionParameter;
use crate::source::Source;
use oxc_ast::ast::{Function, FunctionBody};
use oxc_span::GetSpan;

pub(super) use control::{conditionals, control_increments};
use parameters::function_parameters;

mod control;
mod parameters;

/// Count physical lines occupied by the statements in one function body.
pub(super) fn body_lines(source: &Source, function: &Function) -> usize {
    let Some(body) = function.body.as_ref() else {
        return 0;
    };
    let (Some(first), Some(last)) = (body.statements.first(), body.statements.last()) else {
        return 0;
    };
    source.line_count(ruff_text_size::TextRange::new(
        range(first.span()).start(),
        range(last.span()).end(),
    ))
}

/// Return every parameter property the general callable rules read.
pub(super) fn parameters(source: &Source, function: &Function) -> Vec<FunctionParameter> {
    function_parameters(source, function)
}

pub(super) fn statement_count(body: Option<&FunctionBody>) -> usize {
    body.map_or(0, |held| held.statements.len())
}
