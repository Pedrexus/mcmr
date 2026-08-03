use super::super::collections::is_named;
use super::evidence::ValidatorEvidence;
use super::variants::optional_variant_count;
use crate::walk::{children, expressions, qualified_name, statements};
use ruff_python_ast::Expr;
use serde_json::{Value, json};
use std::collections::BTreeMap;

pub(super) fn validator(
    method: &ruff_python_ast::StmtFunctionDef,
    fields: &BTreeMap<String, bool>,
) -> Option<Value> {
    let kind = method
        .decorator_list
        .iter()
        .find_map(|decorator| validator_kind(&decorator.expression))?;
    let parameters: Vec<&str> = method
        .parameters
        .iter()
        .map(|parameter| parameter.name().as_str())
        .collect();
    let receiver = parameters.first().copied();
    let value = parameters.get(1).copied();
    let parameters = ValidatorParameters { receiver, value };
    let mut evidence = ValidatorEvidence::default();
    for statement in statements(&method.body) {
        for expression in expressions(statement) {
            inspect_validator_expression(expression, parameters, &mut evidence);
        }
    }
    let variant_count = optional_variant_count(method, receiver, fields);
    Some(json!({
        "kind": kind,
        "fields_read": evidence.fields_read,
        "has_self_call": evidence.has_self_call,
        "has_nonfield_access": evidence.receiver_attributes.iter().any(|name| !fields.contains_key(name)),
        "declarative_constraint_count": evidence.declarative_constraint_count,
        "proves_disjoint_optional_variants": variant_count >= 2,
        "variant_count": variant_count,
    }))
}

#[derive(Clone, Copy)]
struct ValidatorParameters<'a> {
    receiver: Option<&'a str>,
    value: Option<&'a str>,
}

fn validator_kind(decorator: &Expr) -> Option<&'static str> {
    let name = qualified_name(decorator);
    match name.rsplit('.').next().unwrap_or(&name) {
        "field_validator" => Some("field"),
        "model_validator" => Some(
            if matches!(decorator, Expr::Call(call)
            if call.arguments.keywords.iter().any(|keyword| {
                keyword.arg.as_ref().is_some_and(|arg| arg == "mode")
                    && matches!(&keyword.value, Expr::StringLiteral(value)
                        if value.value.to_str() == "after")
            })) {
                "model_after"
            } else {
                "other"
            },
        ),
        _ => None,
    }
}

fn inspect_validator_expression(
    expression: &Expr,
    parameters: ValidatorParameters<'_>,
    evidence: &mut ValidatorEvidence,
) {
    inspect_receiver_attribute(expression, parameters, evidence);
    inspect_validator_call(expression, parameters, evidence);
    inspect_validator_comparison(expression, parameters, evidence);
    for child in children(expression) {
        inspect_validator_expression(child, parameters, evidence);
    }
}

fn inspect_receiver_attribute(
    expression: &Expr,
    parameters: ValidatorParameters<'_>,
    evidence: &mut ValidatorEvidence,
) {
    if let Expr::Attribute(attribute) = expression
        && parameters
            .receiver
            .is_some_and(|name| is_named(&attribute.value, name))
    {
        let name = attribute.attr.to_string();
        evidence.fields_read.insert(name.clone());
        evidence.receiver_attributes.insert(name);
    }
}

fn inspect_validator_call(
    expression: &Expr,
    parameters: ValidatorParameters<'_>,
    evidence: &mut ValidatorEvidence,
) {
    if let Expr::Call(call) = expression {
        if matches!(call.func.as_ref(), Expr::Attribute(attribute)
            if parameters.receiver.is_some_and(|name| is_named(&attribute.value, name)))
        {
            evidence.has_self_call = true;
        }
        if matches!(call.func.as_ref(), Expr::Attribute(attribute)
            if matches!(attribute.attr.as_str(), "strip" | "lower" | "upper")
                && parameters.value.is_some_and(|name| is_named(&attribute.value, name)))
        {
            evidence.declarative_constraint_count += 1;
        }
    }
}

fn inspect_validator_comparison(
    expression: &Expr,
    parameters: ValidatorParameters<'_>,
    evidence: &mut ValidatorEvidence,
) {
    if let Expr::Compare(compare) = expression
        && matches!(compare.ops.as_ref(), [_])
        && matches!(compare.comparators.as_ref(), [right]
            if is_number(right)
                && parameters.value.is_some_and(|name| {
                    is_named(&compare.left, name) || is_length_of(&compare.left, name)
                })
            || is_number(&compare.left)
                && parameters.value.is_some_and(|name| is_named(right, name)))
    {
        evidence.declarative_constraint_count += 1;
    }
}

fn is_number(expression: &Expr) -> bool {
    matches!(expression, Expr::NumberLiteral(_))
}

fn is_length_of(expression: &Expr, value: &str) -> bool {
    matches!(expression, Expr::Call(call)
        if qualified_name(&call.func) == "len"
            && matches!(call.arguments.args.as_ref(), [argument] if is_named(argument, value)))
}
