use super::collections::stated;
use super::enum_context::{Bindings, Enums};
use crate::source::Source;
use crate::walk::{blocks, children};
use ruff_python_ast::{Expr, ModModule, Stmt};
use ruff_text_size::Ranged;

mod access;
mod record;
mod scope;

pub use access::AttributeAccess;
pub use record::AttributeAccessRecord;
use scope::Scope;

/// Build every member access one file performs without an intermediate JSON tree.
pub fn attribute_accesses(source: &Source, module: &ModModule) -> AttributeAccessRecord {
    let mut accesses = Vec::new();
    let enums = Enums::of(module);
    let bound = Bindings::of(None, &module.body, &enums);
    accessed(
        source,
        &module.body,
        None,
        &Scope { bound, enums },
        &mut accesses,
    );
    AttributeAccessRecord {
        key: format!("attributeaccessfact:{}", source.relative),
        span: source.span(module.range()),
        language: "python".to_string(),
        accesses,
    }
}

/// Read one block's accesses, carrying the class whose body lexically encloses it.
///
/// The owning flag has to reach the accesses rather than the declaration that establishes it,
/// since every `self.x` a method writes sits in the method's body and never in the `def` line. A
/// nested callable keeps the class holding it and a nested class takes over, which is what the
/// innermost lexical owner means. A callable is also its own binding scope, so the names proven to
/// hold an enum member are rebuilt on the way into one and inherited everywhere else.
fn accessed(
    source: &Source,
    body: &[Stmt],
    owner: Option<&str>,
    scope: &Scope,
    accesses: &mut Vec<AttributeAccess>,
) {
    for statement in body {
        for expression in stated(statement) {
            collect_accesses(source, expression, owner, scope, accesses);
        }
        let opened = opened_scope(statement, scope);
        for block in blocks(statement) {
            accessed(
                source,
                block,
                nested_owner(statement, owner),
                opened.as_ref().unwrap_or(scope),
                accesses,
            );
        }
    }
}

fn nested_owner<'a>(statement: &'a Stmt, owner: Option<&'a str>) -> Option<&'a str> {
    match statement {
        Stmt::ClassDef(item) => Some(item.name.as_str()),
        _ => owner,
    }
}

fn opened_scope(statement: &Stmt, scope: &Scope) -> Option<Scope> {
    match statement {
        Stmt::FunctionDef(item) => Some(Scope {
            bound: Bindings::of(Some(&item.parameters), &item.body, &scope.enums),
            enums: scope.enums.clone(),
        }),
        _ => None,
    }
}

fn collect_accesses(
    source: &Source,
    expression: &Expr,
    owner: Option<&str>,
    scope: &Scope,
    accesses: &mut Vec<AttributeAccess>,
) {
    if let Expr::Attribute(item) = expression {
        let name = item.attr.to_string();
        let receiver = source.slice(item.value.range()).to_string();
        let kind = receiver_kind(&receiver, owner);
        let held = scope.bound.enum_of(&item.value, &scope.enums);
        accesses.push(AttributeAccess {
            name: name.clone(),
            visibility: member_visibility(&name).to_string(),
            is_inside_owning_class: owner.is_some() && kind != "other",
            is_protocol_name: name.starts_with("__") && name.ends_with("__"),
            receiver: access::ReceiverEvidence {
                kind: kind.to_string(),
                text: receiver,
                type_name: held.unwrap_or_default().to_string(),
                type_bases: held.map(|name| scope.enums.bases(name)).unwrap_or_default(),
            },
            node: source.node_of("attribute", item),
        });
    }
    for child in children(expression) {
        collect_accesses(source, child, owner, scope, accesses);
    }
}

fn receiver_kind(receiver: &str, owner: Option<&str>) -> &'static str {
    match receiver {
        "self" | "cls" => "self",
        "super()" => "super",
        _ if owner == Some(receiver) => "owner",
        _ => "other",
    }
}

fn member_visibility(name: &str) -> &'static str {
    if name.starts_with("__") && name.ends_with("__") {
        "public"
    } else if name.starts_with("__") {
        "private"
    } else if name.starts_with('_') {
        "protected"
    } else {
        "public"
    }
}
