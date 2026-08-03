use super::super::collections::is_named;
use super::super::enum_context::bound_name;
use crate::walk::statements;
use crate::walk::{blocks, qualified_name};
use ruff_python_ast::{BoolOp, Expr, Number, Stmt};
use std::collections::{BTreeMap, BTreeSet};

pub(super) fn optional_variant_count(
    method: &ruff_python_ast::StmtFunctionDef,
    receiver: Option<&str>,
    fields: &BTreeMap<String, bool>,
) -> usize {
    let Some(receiver) = receiver else {
        return 0;
    };
    if method
        .parameters
        .iter()
        .any(|parameter| parameter.name().as_str() == "sum")
        || statements(&method.body).iter().any(|statement| {
            matches!(statement, Stmt::Assign(assignment)
                if assignment.targets.iter().any(|target| bound_name(target) == "sum"))
                || matches!(statement, Stmt::AnnAssign(assignment)
                    if bound_name(&assignment.target) == "sum")
                || matches!(statement, Stmt::AugAssign(assignment)
                    if bound_name(&assignment.target) == "sum")
        })
    {
        return 0;
    }
    variant_count_in_blocks(&method.body, receiver, fields)
}

fn variant_count_in_blocks(
    body: &[Stmt],
    receiver: &str,
    fields: &BTreeMap<String, bool>,
) -> usize {
    let direct = body
        .iter()
        .enumerate()
        .filter_map(|(index, statement)| {
            let Stmt::If(branch) = statement else {
                return None;
            };
            let Expr::Compare(compare) = branch.test.as_ref() else {
                return None;
            };
            if !matches!(compare.ops.as_ref(), [ruff_python_ast::CmpOp::Gt])
                || !matches!(compare.comparators.as_ref(), [Expr::NumberLiteral(number)]
                    if matches!(&number.value, Number::Int(value) if value == &ruff_python_ast::Int::ONE))
                || !raises_validation_error(&branch.body)
            {
                return None;
            }
            let sum = match compare.left.as_ref() {
                Expr::Call(call) => Some(call),
                Expr::Name(name) => index.checked_sub(1).and_then(|previous| {
                    let Stmt::Assign(assignment) = &body[previous] else {
                        return None;
                    };
                    matches!(assignment.targets.as_slice(), [target]
                        if bound_name(target) == name.id.as_str())
                    .then_some(assignment.value.as_ref())
                    .and_then(|value| match value {
                        Expr::Call(call) => Some(call),
                        _ => None,
                    })
                }),
                _ => None,
            }?;
            if qualified_name(&sum.func) != "sum" || sum.arguments.args.len() != 1 {
                return None;
            }
            let variants =
                variant_groups_from_sum(&sum.arguments.args[0], &body[..index], receiver)?;
            let names: Vec<&str> = variants
                .iter()
                .flat_map(|group| group.iter().map(String::as_str))
                .collect();
            let distinct: BTreeSet<&str> = names.iter().copied().collect();
            (variants.len() >= 2
                && distinct.len() == names.len()
                && names.iter().all(|field| fields.get(*field) == Some(&true)))
            .then_some(variants.len())
        })
        .max()
        .unwrap_or_default();
    body.iter()
        .flat_map(blocks)
        .map(|nested| variant_count_in_blocks(nested, receiver, fields))
        .fold(direct, usize::max)
}

fn variant_groups_from_sum(
    expression: &Expr,
    preceding: &[Stmt],
    receiver: &str,
) -> Option<Vec<Vec<String>>> {
    if let Some(groups) = variant_groups(expression, receiver) {
        return Some(groups);
    }
    let Expr::Generator(generator) = expression else {
        return None;
    };
    let [clause] = generator.generators.as_slice() else {
        return None;
    };
    let Expr::Name(target) = &clause.target else {
        return None;
    };
    let Expr::Name(iterable) = &clause.iter else {
        return None;
    };
    if !clause.ifs.is_empty() || !named_presence(&generator.elt, target.id.as_str()) {
        return None;
    }
    let values = preceding.iter().rev().find_map(|statement| {
        let Stmt::Assign(assignment) = statement else {
            return None;
        };
        matches!(assignment.targets.as_slice(), [bound]
            if bound_name(bound) == iterable.id.as_str())
        .then_some(assignment.value.as_ref())
    })?;
    let elements = match values {
        Expr::Tuple(tuple) => tuple.elts.as_slice(),
        Expr::List(list) => list.elts.as_slice(),
        _ => return None,
    };
    elements
        .iter()
        .map(|value| receiver_field(value, receiver).map(|field| vec![field]))
        .collect()
}

fn named_presence(expression: &Expr, name: &str) -> bool {
    matches!(expression, Expr::Compare(compare)
        if matches!(compare.left.as_ref(), Expr::Name(value) if value.id == name)
            && matches!(compare.ops.as_ref(), [ruff_python_ast::CmpOp::IsNot])
            && matches!(compare.comparators.as_ref(), [Expr::NoneLiteral(_)]))
}

fn receiver_field(expression: &Expr, receiver: &str) -> Option<String> {
    let Expr::Attribute(attribute) = expression else {
        return None;
    };
    is_named(&attribute.value, receiver).then(|| attribute.attr.to_string())
}

fn variant_groups(expression: &Expr, receiver: &str) -> Option<Vec<Vec<String>>> {
    let values: &[Expr] = match expression {
        Expr::Tuple(tuple) => &tuple.elts,
        Expr::List(list) => &list.elts,
        _ => return None,
    };
    values
        .iter()
        .map(|value| variant_group(value, receiver))
        .collect()
}

fn variant_group(expression: &Expr, receiver: &str) -> Option<Vec<String>> {
    match expression {
        Expr::BoolOp(group) if group.op == BoolOp::Or => group
            .values
            .iter()
            .map(|value| optional_presence(value, receiver))
            .collect(),
        _ => optional_presence(expression, receiver).map(|field| vec![field]),
    }
}

fn optional_presence(expression: &Expr, receiver: &str) -> Option<String> {
    let Expr::Compare(compare) = expression else {
        return None;
    };
    let [Expr::NoneLiteral(_)] = compare.comparators.as_ref() else {
        return None;
    };
    let Expr::Attribute(attribute) = compare.left.as_ref() else {
        return None;
    };
    (matches!(compare.ops.as_ref(), [ruff_python_ast::CmpOp::IsNot])
        && is_named(&attribute.value, receiver))
    .then(|| attribute.attr.to_string())
}

fn raises_validation_error(body: &[Stmt]) -> bool {
    matches!(body, [Stmt::Raise(raised)]
    if raised.exc.as_deref().is_some_and(|error| {
        let name = qualified_name(error);
        matches!(name.rsplit('.').next(), Some("ValueError" | "PydanticCustomError"))
    }))
}
