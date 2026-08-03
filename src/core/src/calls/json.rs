use super::{resolution::ResolutionIndex, resolved::ResolvedCall};
use crate::graph;
use std::collections::BTreeMap;

struct SyntaxResolution {
    shadowed: bool,
    constructor: bool,
}

pub(super) fn enrich_expression_names(
    expression: &mut serde_json::Value,
    resolved: &BTreeMap<(u64, u64, u64, u64), String>,
) {
    apply_expression_name(expression, resolved);
    enrich_array(expression, "arguments", resolved);
    enrich_entry_values(expression, resolved);
}

fn apply_expression_name(
    expression: &mut serde_json::Value,
    resolved: &BTreeMap<(u64, u64, u64, u64), String>,
) {
    if let Some(span) = expression.get("node").and_then(|node| node.get("span")) {
        let key = (
            span["start_line"].as_u64().unwrap_or_default(),
            span["start_column"].as_u64().unwrap_or_default(),
            span["end_line"].as_u64().unwrap_or_default(),
            span["end_column"].as_u64().unwrap_or_default(),
        );
        if let Some(qualified_name) = resolved.get(&key) {
            expression["qualified_name"] = qualified_name.clone().into();
        }
    }
}

fn enrich_array(
    expression: &mut serde_json::Value,
    field: &str,
    resolved: &BTreeMap<(u64, u64, u64, u64), String>,
) {
    let Some(children) = expression
        .get_mut(field)
        .and_then(serde_json::Value::as_array_mut)
    else {
        return;
    };
    for child in children {
        enrich_expression_names(child, resolved);
    }
}

fn enrich_entry_values(
    expression: &mut serde_json::Value,
    resolved: &BTreeMap<(u64, u64, u64, u64), String>,
) {
    let Some(entries) = expression
        .get_mut("entries")
        .and_then(serde_json::Value::as_array_mut)
    else {
        return;
    };
    for value in entries
        .iter_mut()
        .filter_map(|entry| entry.get_mut("value"))
    {
        enrich_expression_names(value, resolved);
    }
}

pub(super) fn enrich_calls(
    calls: &mut [serde_json::Value],
    resolutions: &mut ResolutionIndex<'_>,
    provider_classifies_python_syntax: Option<bool>,
) {
    for call in calls {
        enrich_call(call, resolutions, provider_classifies_python_syntax);
    }
}

fn enrich_call(
    call: &mut serde_json::Value,
    resolutions: &mut ResolutionIndex<'_>,
    provider_classifies_python_syntax: Option<bool>,
) {
    let path = call["path"]
        .as_str()
        .expect("a call path must be text")
        .to_string();
    let line = call["node"]["span"]["start_line"]
        .as_u64()
        .and_then(|line| usize::try_from(line).ok())
        .expect("a call node line must fit usize");
    let Some(answer) = resolutions.next(&path, line) else {
        return;
    };
    let original = call["qualified_name"]
        .as_str()
        .expect("a call qualified_name must be text")
        .to_string();
    let syntax_shadowed = provider_boolean(call, "is_shadowed", provider_classifies_python_syntax);
    let syntax_constructor =
        provider_boolean(call, "is_constructor", provider_classifies_python_syntax);
    let graph_shadowed =
        !original.contains('.') && graph::is_builtin(&original) && answer.is_first_party;
    apply_resolution(
        call,
        answer,
        provider_classifies_python_syntax,
        SyntaxResolution {
            shadowed: syntax_shadowed || graph_shadowed,
            constructor: syntax_constructor || answer.is_constructor,
        },
    );
}

fn provider_boolean(
    call: &serde_json::Value,
    field: &str,
    provider_classifies_python_syntax: Option<bool>,
) -> bool {
    provider_classifies_python_syntax
        .filter(|classifies| *classifies)
        .and_then(|_| call.get(field))
        .and_then(serde_json::Value::as_bool)
        .unwrap_or(false)
}

fn apply_resolution(
    call: &mut serde_json::Value,
    answer: &ResolvedCall,
    provider_classifies_python_syntax: Option<bool>,
    syntax: SyntaxResolution,
) {
    let record = call.as_object_mut().expect("a call must be an object");
    if provider_classifies_python_syntax != Some(false)
        || answer.resolution != graph::Resolution::Unresolved
    {
        record.insert(
            "qualified_name".to_string(),
            answer.qualified_name.clone().into(),
        );
    }
    if provider_classifies_python_syntax.is_none() {
        return;
    }
    for (name, stated) in [
        ("is_external", answer.is_external),
        ("is_first_party", answer.is_first_party),
        ("is_standard_library", answer.is_standard_library),
        ("is_shadowed", syntax.shadowed),
        ("is_constructor", syntax.constructor),
    ] {
        if stated {
            record.insert(name.to_string(), true.into());
        } else {
            record.remove(name);
        }
    }
}
