use super::super::super::functions::support::root_name;
use ruff_python_ast::{Arguments, Expr, Parameters};
use std::collections::BTreeSet;

/// Whether one call restates exactly the parameters one signature declares, in their own order.
pub(super) fn passes_through(declared: &Parameters, arguments: &Arguments) -> bool {
    declared_positional(declared) == passed_positional(arguments)
        && declared_keywords(declared) == passed_keywords(arguments)
}

fn declared_positional(declared: &Parameters) -> Vec<String> {
    declared
        .posonlyargs
        .iter()
        .chain(declared.args.iter())
        .map(|parameter| parameter.parameter.name.to_string())
        .skip(1)
        .chain(
            declared
                .vararg
                .as_ref()
                .map(|parameter| format!("*{}", parameter.name)),
        )
        .collect()
}

fn passed_positional(arguments: &Arguments) -> Vec<String> {
    arguments
        .args
        .iter()
        .map(|argument| match argument {
            Expr::Name(held) => held.id.to_string(),
            Expr::Starred(held) => format!("*{}", root_name(&held.value)),
            _ => String::new(),
        })
        .collect()
}

fn declared_keywords(declared: &Parameters) -> BTreeSet<String> {
    declared
        .kwonlyargs
        .iter()
        .map(|parameter| parameter.parameter.name.to_string())
        .chain(
            declared
                .kwarg
                .as_ref()
                .map(|parameter| format!("**{}", parameter.name)),
        )
        .collect()
}

fn passed_keywords(arguments: &Arguments) -> BTreeSet<String> {
    arguments
        .keywords
        .iter()
        .map(|keyword| match (&keyword.arg, &keyword.value) {
            (Some(name), Expr::Name(held)) if held.id.as_str() == name.as_str() => {
                name.to_string()
            }
            (None, value) => format!("**{}", root_name(value)),
            _ => String::new(),
        })
        .collect()
}
