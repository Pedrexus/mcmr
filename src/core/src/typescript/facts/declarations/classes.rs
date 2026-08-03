use super::shared::{declaration_visibility, declared_class, member_name, member_visibility};
use crate::protocol::JsonObject;
use crate::source::Source;
use crate::typescript::support::base;
use crate::typescript::support::range;
use oxc_ast::ast::{Class, ClassElement, MethodDefinition, Program};
use oxc_span::GetSpan;
use serde_json::{Value, json};

pub(in crate::typescript::facts) fn class_fact(source: &Source, program: &Program) -> Value {
    let classes: Vec<Value> = program
        .body
        .iter()
        .filter_map(|statement| {
            let class = declared_class(statement)?;
            let name = class.id.as_ref()?.name.to_string();
            Some(class_record(
                source,
                class,
                name,
                declaration_visibility(statement),
            ))
        })
        .collect();
    JsonObject::new(base(source, &format!("classes:{}", source.relative)))
        .merged(json!({"classes": classes}))
}

fn class_record(
    source: &Source,
    class: &Class<'_>,
    name: String,
    visibility: crate::graph::Visibility,
) -> Value {
    json!({
        "name": name,
        "path": source.relative.clone(),
        "span": source.span(range(class.span)),
        "source": source.slice(range(class.span)),
        "scope": "module",
        "visibility": visibility,
        "direct_bases": direct_bases(source, class),
        "methods": methods(source, class),
        "field_count": field_count(class),
    })
}

fn direct_bases(source: &Source, class: &Class<'_>) -> Vec<String> {
    class
        .super_class
        .as_ref()
        .map(|base| vec![source.slice(range(base.span())).to_string()])
        .unwrap_or_default()
}

fn field_count(class: &Class<'_>) -> usize {
    class
        .body
        .body
        .iter()
        .filter(|member| matches!(member, ClassElement::PropertyDefinition(_)))
        .count()
}

fn method_kind(method: &MethodDefinition<'_>) -> &'static str {
    if method.kind.is_constructor() {
        "constructor"
    } else if method.kind.is_accessor() {
        "property"
    } else if method.r#static {
        "static_method"
    } else {
        "method"
    }
}

fn method_record(source: &Source, method: &MethodDefinition<'_>) -> Option<Value> {
    Some(json!({
        "name": member_name(method)?,
        "span": source.span(range(method.span)),
        "source": source.slice(range(method.span)),
        "kind": method_kind(method),
        "visibility": member_visibility(method),
    }))
}

fn methods(source: &Source, class: &Class<'_>) -> Vec<Value> {
    class
        .body
        .body
        .iter()
        .filter_map(|member| match member {
            ClassElement::MethodDefinition(method) => method_record(source, method),
            _ => None,
        })
        .collect()
}
