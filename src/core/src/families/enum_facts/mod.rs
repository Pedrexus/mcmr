use crate::source::Source;
use crate::walk::{qualified_name, walk};
use ruff_python_ast::{Expr, ModModule, Number, Stmt};
use ruff_text_size::Ranged;
use serde_json::{Value, json};

/// Every enumeration one file declares, with the values its members state.
///
/// The two lists this family carries beside the declarations are `scopes` and `files`, and neither
/// is a question one file can answer. Where a reused enum belongs is decided by every module that
/// imports it, and whether a shared `enums` package holds one enum per module is a claim about the
/// package rather than about any file in it. Both need a repository pass the way `ExceptionFact`
/// has one, so this builder states the declarations and leaves the two lists to it.
pub fn enums(source: &Source, module: &ModModule) -> Value {
    let declared: Vec<Value> = walk(module)
        .into_iter()
        .filter_map(|statement| match statement {
            Stmt::ClassDef(item) => enum_analysis(source, item),
            _ => None,
        })
        .collect();
    json!({"enums": declared})
}

pub(crate) fn is_enum(bases: &[String]) -> bool {
    enum_kind(bases).is_some()
}

fn enum_analysis(source: &Source, item: &ruff_python_ast::StmtClassDef) -> Option<Value> {
    let bases: Vec<String> = item
        .arguments
        .as_ref()
        .map(|arguments| arguments.args.iter().map(qualified_name).collect())
        .unwrap_or_default();
    let kind = enum_kind(&bases)?;
    let members: Vec<Value> = item
        .body
        .iter()
        .enumerate()
        .filter_map(|(position, member)| enum_member(source, member, position, kind))
        .collect();
    Some(json!({
        "name": item.name.to_string(),
        "kind": kind,
        "members": members,
        "overrides_generate_next_value": item
            .body
            .iter()
            .any(|member| matches!(member, Stmt::FunctionDef(function)
                if function.name.as_str() == "_generate_next_value_")),
    }))
}

pub(super) fn enum_kind(bases: &[String]) -> Option<&'static str> {
    bases
        .iter()
        .find_map(|base| match base.rsplit('.').next().unwrap_or(base) {
            "StrEnum" => Some("str_enum"),
            "IntEnum" => Some("int_enum"),
            "IntFlag" => Some("int_flag"),
            "Flag" => Some("flag"),
            "Enum" => Some("enum"),
            _ => None,
        })
}

fn enum_member(source: &Source, member: &Stmt, position: usize, kind: &str) -> Option<Value> {
    let Stmt::Assign(assignment) = member else {
        return None;
    };
    let Expr::Name(target) = assignment.targets.first()? else {
        return None;
    };
    let name = target.id.to_string();
    let automatic = if kind == "str_enum" {
        json!(name.to_lowercase())
    } else {
        json!(position + 1)
    };
    Some(json!({
        "name": name,
        "explicit_value": match assignment.value.as_ref() {
            Expr::StringLiteral(literal) => json!(literal.value.to_str()),
            Expr::NumberLiteral(literal) => match &literal.value {
                Number::Int(value) => value
                    .as_i64()
                    .map_or_else(|| json!(value.to_string()), |value| json!(value)),
                _ => json!(format!("{:?}", literal.value)),
            },
            _ => json!(""),
        },
        "standard_auto_value": automatic,
        "value_node": source.node("expression", assignment.value.range()),
    }))
}
