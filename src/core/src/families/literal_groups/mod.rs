use super::collections::stated;
use super::enum_context::Enums;
use crate::source::Source;
use crate::walk::{children, qualified_name, walk};
use ruff_python_ast::{Expr, ModModule};
use serde_json::{Value, json};
use std::collections::BTreeMap;

/// Every equal string literal one file repeats in one role, and the enum tables beside them.
///
/// Two strings that read the same in two different places are not the same decision, so a group is
/// keyed by the role as well as the value. A keyword name on a call and one side of an equality
/// test are the two roles a project-owned value takes, and everything else is where a repeated
/// string is ordinary vocabulary rather than a policy, which is what the exclusion says out loud.
pub fn literal_groups(source: &Source, module: &ModModule) -> Value {
    let mut counts: BTreeMap<(String, LiteralRole), usize> = BTreeMap::new();
    for statement in walk(module) {
        for expression in stated(statement) {
            count_literals(expression, LiteralRole::Value, &mut counts);
        }
    }
    let groups: Vec<Value> = counts
        .into_iter()
        .filter(|((value, _), count)| *count > 1 && value.len() > 3)
        .map(|((value, role), count)| {
            json!({
                "value": value,
                "role": role.as_str(),
                "occurrence_count": count,
                "files": [source.relative.clone()],
                "is_excluded_vocabulary": role == LiteralRole::Value,
            })
        })
        .collect();
    json!({
        "string_groups": groups,
        "enum_metadata_maps": enum_metadata_maps(module),
    })
}

#[derive(Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
enum LiteralRole {
    Value,
    Keyword,
    Comparison,
}

impl LiteralRole {
    fn as_str(self) -> &'static str {
        match self {
            Self::Value => "value",
            Self::Keyword => "keyword",
            Self::Comparison => "comparison",
        }
    }
}

fn count_literals(
    expression: &Expr,
    role: LiteralRole,
    counts: &mut BTreeMap<(String, LiteralRole), usize>,
) {
    if let Expr::StringLiteral(item) = expression {
        *counts
            .entry((item.value.to_str().to_string(), role))
            .or_default() += 1;
    }
    for (child, held) in literal_roles(expression, role) {
        count_literals(child, held, counts);
    }
}

/// Return the children of one expression, each with the role the literals inside it occupy.
fn literal_roles(expression: &Expr, role: LiteralRole) -> Vec<(&Expr, LiteralRole)> {
    match expression {
        Expr::Call(item) => item
            .arguments
            .args
            .iter()
            .map(|argument| (argument, LiteralRole::Value))
            .chain(
                item.arguments
                    .keywords
                    .iter()
                    .map(|keyword| (&keyword.value, LiteralRole::Keyword)),
            )
            .chain(std::iter::once((item.func.as_ref(), LiteralRole::Value)))
            .collect(),
        Expr::Compare(item) if matches!(item.ops.as_ref(), [ruff_python_ast::CmpOp::Eq]) => {
            std::iter::once((item.left.as_ref(), LiteralRole::Comparison))
                .chain(
                    item.comparators
                        .iter()
                        .map(|held| (held, LiteralRole::Comparison)),
                )
                .collect()
        }
        _ => children(expression)
            .into_iter()
            .map(|child| (child, role))
            .collect(),
    }
}

/// Return every literal mapping one file keys entirely by members of one enum it declares.
fn enum_metadata_maps(module: &ModModule) -> Vec<Value> {
    let enums = Enums::of(module);
    let mut found = Vec::new();
    for statement in walk(module) {
        for expression in stated(statement) {
            collect_metadata_maps(expression, &enums, &mut found);
        }
    }
    found
}

fn collect_metadata_maps(expression: &Expr, enums: &Enums, found: &mut Vec<Value>) {
    if let Expr::Dict(item) = expression
        && !item.items.is_empty()
    {
        let members: Vec<(String, String)> = item
            .items
            .iter()
            .filter_map(|entry| enum_member_key(entry.key.as_ref()?, enums))
            .collect();
        let values: Vec<String> = item
            .items
            .iter()
            .filter_map(|entry| match &entry.value {
                Expr::StringLiteral(held) => Some(held.value.to_str().to_string()),
                _ => None,
            })
            .collect();
        let owner = members.first().map(|(held, _)| held.clone());
        found.push(json!({
            "enum_name": owner.clone().unwrap_or_default(),
            "keys": members.iter().map(|(_, held)| held).collect::<Vec<_>>(),
            "values": values.clone(),
            "all_keys_resolve_to_enum": members.len() == item.items.len()
                && values.len() == item.items.len()
                && members.iter().all(|(held, _)| Some(held) == owner.as_ref()),
        }));
    }
    for child in children(expression) {
        collect_metadata_maps(child, enums, found);
    }
}

/// Return the enumeration and member name one mapping key states, when it names one.
fn enum_member_key(key: &Expr, enums: &Enums) -> Option<(String, String)> {
    let Expr::Attribute(item) = key else {
        return None;
    };
    let owner = qualified_name(&item.value);
    enums.holds(&owner).then(|| {
        (
            owner,
            format!("{}.{}", qualified_name(&item.value), item.attr),
        )
    })
}
