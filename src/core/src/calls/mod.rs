use crate::graph;
use crate::protocol::Span;
use crate::source::is_test_path;
use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

mod evidence;
mod expression;
mod json;
mod mapping;
mod reachability;
mod resolution;
mod resolved;
mod site;

pub use evidence::EvidenceRecord;
pub use expression::Expression;
use json::{
    enrich_calls as enrich_json_calls, enrich_expression_names as enrich_json_expression_names,
};
pub use mapping::MappingEntry;
pub(crate) use reachability::TestReachability;
pub(crate) use resolution::ResolutionIndex;
pub(crate) use resolved::ResolvedCall;
pub(crate) use resolved::resolutions;
pub use site::CallSite;

/// One call fact after repository name resolution has completed.
#[derive(Clone, Debug, Deserialize, Serialize)]
pub struct CallRecord {
    pub key: String,
    pub span: Span,
    pub language: String,
    #[serde(default, skip_serializing_if = "std::ops::Not::not")]
    pub is_test: bool,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub evidence: Vec<EvidenceRecord>,
    #[serde(default)]
    pub calls: Vec<CallSite>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub module_bindings: Vec<String>,
}

impl CallRecord {
    /// Start one provider record with its identity and neutral child collections.
    pub fn new(key: String, span: Span, language: &str) -> Self {
        let is_test = is_test_path(&span.path);
        Self {
            key,
            span,
            language: language.to_string(),
            is_test,
            evidence: Vec::new(),
            calls: Vec::new(),
            module_bindings: Vec::new(),
        }
    }

    /// Serialize one typed provider record for the independent JSON protocol.
    pub fn into_json(self) -> serde_json::Value {
        serde_json::to_value(self).expect("a typed call record must serialize")
    }
}

/// Join one bounded compatibility batch onto graph resolution for the same call sites.
pub(crate) fn enrich_facts(
    family: &str,
    facts: &mut [serde_json::Value],
    resolutions: &mut ResolutionIndex<'_>,
) {
    match family {
        "CallFact" => {
            for fact in facts {
                enrich_call_fact(fact, resolutions);
            }
        }
        "TestFunctionFact" => {
            for fact in facts {
                enrich_test_fact(fact, resolutions);
            }
        }
        _ => {}
    }
}

pub(crate) fn enrich_test_reach(facts: &mut [serde_json::Value], reachability: &TestReachability) {
    for fact in facts {
        let tests = fact
            .get_mut("tests")
            .and_then(serde_json::Value::as_array_mut)
            .expect("TestFunctionFact.tests must be an array");
        for test in tests {
            let path = test["path"]
                .as_str()
                .expect("TestFunction.path must be text")
                .to_string();
            let line = test["node"]["span"]["start_line"]
                .as_u64()
                .and_then(|value| usize::try_from(value).ok())
                .unwrap_or(1);
            let targets = test["calls"]
                .as_array()
                .expect("TestFunction.calls must be an array")
                .iter()
                .filter_map(|call| call.get("target_id")?.as_str().map(str::to_string))
                .collect::<Vec<_>>();
            test["direct_targets"] = serde_json::json!(reachability.direct(&path, line, &targets));
            test["reachable_targets"] =
                serde_json::json!(reachability.reachable(&path, line, &targets));
        }
    }
}

fn enrich_call_fact(fact: &mut serde_json::Value, resolutions: &mut ResolutionIndex<'_>) {
    let provider_classifies_python_syntax = fact["language"]
        .as_str()
        .expect("CallFact.language must be text")
        == "python";
    let calls = fact
        .get_mut("calls")
        .and_then(serde_json::Value::as_array_mut)
        .expect("CallFact.calls must be an array");
    enrich_json_calls(calls, resolutions, Some(provider_classifies_python_syntax));
    let names = resolved_json_expressions(calls);
    for call in calls {
        if let Some(arguments) = call
            .get_mut("arguments")
            .and_then(serde_json::Value::as_array_mut)
        {
            for expression in arguments {
                enrich_json_expression_names(expression, &names);
            }
        }
        if let Some(receiver) = call.get_mut("receiver") {
            enrich_json_expression_names(receiver, &names);
        }
    }
}

fn enrich_test_fact(fact: &mut serde_json::Value, resolutions: &mut ResolutionIndex<'_>) {
    let tests = fact
        .get_mut("tests")
        .and_then(serde_json::Value::as_array_mut)
        .expect("TestFunctionFact.tests must be an array");
    for test in tests {
        let calls = test
            .get_mut("calls")
            .and_then(serde_json::Value::as_array_mut)
            .expect("TestFunction.calls must be an array");
        enrich_json_calls(calls, resolutions, None);
    }
}

fn resolved_json_expressions(
    calls: &[serde_json::Value],
) -> BTreeMap<(u64, u64, u64, u64), String> {
    calls
        .iter()
        .filter_map(|call| {
            let span = call.get("node")?.get("span")?;
            Some((
                (
                    span.get("start_line")?.as_u64()?,
                    span.get("start_column")?.as_u64()?,
                    span.get("end_line")?.as_u64()?,
                    span.get("end_column")?.as_u64()?,
                ),
                call.get("qualified_name")?.as_str()?.to_string(),
            ))
        })
        .collect()
}

/// Join repository resolution directly onto typed call provider records.
pub(crate) fn enrich_records(facts: &mut [CallRecord], resolutions: &mut ResolutionIndex<'_>) {
    for fact in facts {
        enrich_record_calls(fact, resolutions);
        let names = fact
            .calls
            .iter()
            .map(|call| (call.span_key(), call.qualified_name.clone()))
            .collect::<BTreeMap<_, _>>();
        for call in &mut fact.calls {
            enrich_record_expressions(call, &names);
        }
    }
}

fn enrich_record_calls(fact: &mut CallRecord, resolutions: &mut ResolutionIndex<'_>) {
    if fact.language == "python" {
        for call in &mut fact.calls {
            enrich_python_record_call(call, resolutions);
        }
    } else {
        for call in &mut fact.calls {
            enrich_resolved_record_call(call, resolutions);
        }
    }
}

fn enrich_record_expressions(
    call: &mut CallSite,
    names: &BTreeMap<(usize, usize, usize, usize), String>,
) {
    for expression in &mut call.arguments {
        enrich_expression_names(expression, names);
    }
    if let Some(receiver) = &mut call.receiver {
        enrich_expression_names(receiver, names);
    }
}

fn enrich_python_record_call(call: &mut CallSite, resolutions: &mut ResolutionIndex<'_>) {
    let Some(answer) = resolutions.next(&call.path, call.node.span.start_line) else {
        return;
    };
    let graph_shadowed = !call.qualified_name.contains('.')
        && graph::is_builtin(&call.qualified_name)
        && answer.is_first_party;
    call.target_id.clone_from(&answer.target_id);
    call.qualified_name.clone_from(&answer.qualified_name);
    call.is_external = answer.is_external;
    call.is_first_party = answer.is_first_party;
    call.is_standard_library = answer.is_standard_library;
    call.is_shadowed |= graph_shadowed;
    call.is_constructor |= answer.is_constructor;
}

fn enrich_resolved_record_call(call: &mut CallSite, resolutions: &mut ResolutionIndex<'_>) {
    let Some(answer) = resolutions.next(&call.path, call.node.span.start_line) else {
        return;
    };
    call.target_id.clone_from(&answer.target_id);
    if answer.resolution != graph::Resolution::Unresolved {
        call.qualified_name.clone_from(&answer.qualified_name);
    }
}

fn enrich_expression_names(
    expression: &mut Expression,
    resolved: &BTreeMap<(usize, usize, usize, usize), String>,
) {
    if let Some(node) = &expression.node {
        let key = (
            node.span.start_line,
            node.span.start_column,
            node.span.end_line,
            node.span.end_column,
        );
        if let Some(qualified_name) = resolved.get(&key) {
            expression.qualified_name.clone_from(qualified_name);
        }
    }
    for argument in &mut expression.arguments {
        enrich_expression_names(argument, resolved);
    }
    for entry in &mut expression.entries {
        enrich_expression_names(&mut entry.value, resolved);
    }
}
