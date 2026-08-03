use super::super::support::range;
use crate::functions::FunctionParameter;
use crate::source::Source;
use oxc_ast::ast::{BindingPattern, Expression, Function, TSTypeAnnotation};
use oxc_span::GetSpan;

pub(super) fn function_parameters(source: &Source, function: &Function) -> Vec<FunctionParameter> {
    let ordinary = function
        .params
        .items
        .iter()
        .map(|item| ordinary_parameter(source, item));
    let rest = function
        .params
        .rest
        .iter()
        .map(|item| rest_parameter(source, item));
    ordinary.chain(rest).collect()
}

fn annotation_text(source: &Source, annotation: &TSTypeAnnotation<'_>) -> String {
    source
        .slice(range(annotation.span))
        .trim_start_matches(':')
        .trim()
        .to_string()
}

fn ordinary_parameter(
    source: &Source,
    parameter: &oxc_ast::ast::FormalParameter<'_>,
) -> FunctionParameter {
    let requirement = match !parameter.optional && parameter.initializer.is_none() {
        true => Requirement::Required,
        false => Requirement::Optional,
    };
    parameter_record(
        source,
        &parameter.pattern,
        parameter.type_annotation.as_deref(),
        requirement,
        parameter.initializer.as_deref(),
    )
}

fn parameter_name(source: &Source, pattern: &BindingPattern<'_>) -> String {
    pattern
        .get_identifier_name()
        .map(|name| name.to_string())
        .unwrap_or_else(|| source.slice(range(pattern.span())).to_string())
}

fn parameter_record(
    source: &Source,
    pattern: &BindingPattern<'_>,
    annotation: Option<&TSTypeAnnotation<'_>>,
    requirement: Requirement,
    default: Option<&Expression<'_>>,
) -> FunctionParameter {
    let mut fact = FunctionParameter::named(parameter_name(source, pattern));
    fact.type_name = annotation
        .map(|held| annotation_text(source, held))
        .unwrap_or_default();
    fact.contract.is_positional_only = true;
    fact.contract.is_required_by_external_contract = requirement == Requirement::Required;
    fact.contract.has_boolean_annotation = fact.type_name == "boolean";
    fact.contract.has_boolean_default = matches!(default, Some(Expression::BooleanLiteral(_)));
    fact
}

fn rest_parameter(
    source: &Source,
    parameter: &oxc_ast::ast::FormalParameterRest<'_>,
) -> FunctionParameter {
    parameter_record(
        source,
        &parameter.rest.argument,
        parameter.type_annotation.as_deref(),
        Requirement::Optional,
        None,
    )
}

#[derive(Clone, Copy, PartialEq, Eq)]
enum Requirement {
    Optional,
    Required,
}
