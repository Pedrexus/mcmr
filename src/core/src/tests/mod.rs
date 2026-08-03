use super::*;
use crate::protocol::Request;
use std::collections::BTreeMap;

fn request(root: &str) -> Request {
    Request {
        root: root.to_string(),
        families: vec!["ModuleFact".to_string(), "FunctionFact".to_string()],
        suffixes: vec![".py".to_string()],
        graph: false,
        stream: false,
        fingerprint_only: false,
        python_standard_library: Vec::new(),
    }
}

fn python_corpus() -> &'static str {
    concat!(env!("CARGO_MANIFEST_DIR"), "/../api/mcmr")
}

#[test]
fn parallel_extraction_is_stable_between_runs() {
    let root = python_corpus();

    let first = run(&request(root)).expect("the corpus reads");
    let second = run(&request(root)).expect("the corpus reads");

    assert!(first.stats.fact_count > 0);
    assert_eq!(
        serde_json::to_string(&first.facts).expect("facts serialize"),
        serde_json::to_string(&second.facts).expect("facts serialize"),
        "documents arrive sorted and workers deliver in that order, so two runs must agree"
    );
}

#[test]
fn streamed_and_buffered_extraction_produce_the_same_facts() {
    let root = python_corpus();
    let request = request(root);
    let buffered = run(&request).expect("the corpus reads");
    let mut facts: BTreeMap<String, Vec<serde_json::Value>> = BTreeMap::new();

    let stats = run_stream(&request, |family, mut produced| {
        facts.entry(family).or_default().append(&mut produced);
        Ok(())
    })
    .expect("the corpus streams");

    assert_eq!(facts, buffered.facts);
    assert_eq!(stats.fact_count, buffered.stats.fact_count);
    assert_eq!(
        stats.parse_failure_count,
        buffered.stats.parse_failure_count
    );
}

#[test]
fn typed_function_rows_and_the_json_fallback_are_exactly_the_same_facts() {
    let root = python_corpus();
    let mut request = request(root);
    request.families = vec!["FunctionFact".to_string()];
    let mut legacy = Vec::new();

    let output = run_session(
        &request,
        &["FunctionFact".to_string()],
        |family, mut produced| {
            assert_eq!(family, "FunctionFact");
            legacy.append(&mut produced);
            Ok(())
        },
    )
    .expect("the session reads the corpus");
    let typed = output
        .facts
        .functions
        .into_iter()
        .map(functions::FunctionRecord::into_json)
        .collect::<Vec<_>>();

    assert_eq!(typed.len(), legacy.len());
    for (index, (typed, legacy)) in typed.iter().zip(&legacy).enumerate() {
        assert_eq!(typed, legacy, "FunctionFact parity differs at row {index}");
    }
    assert_eq!(output.stats.fact_count, typed.len());
}

#[test]
fn typed_call_rows_and_the_json_fallback_are_exactly_the_same_facts() {
    let root = python_corpus();
    let mut request = request(root);
    request.families = vec!["CallFact".to_string()];
    let mut legacy = Vec::new();

    let output = run_session(
        &request,
        &["CallFact".to_string()],
        |family, mut produced| {
            assert_eq!(family, "CallFact");
            legacy.append(&mut produced);
            Ok(())
        },
    )
    .expect("the session reads the corpus");
    let typed = output
        .facts
        .calls
        .into_iter()
        .map(calls::CallRecord::into_json)
        .collect::<Vec<_>>();

    assert_eq!(typed.len(), legacy.len());
    for (index, (typed, legacy)) in typed.iter().zip(&legacy).enumerate() {
        let typed_calls = typed["calls"].as_array().expect("typed calls are an array");
        let legacy_calls = legacy["calls"]
            .as_array()
            .expect("compatibility calls are an array");
        assert_eq!(typed_calls.len(), legacy_calls.len());
        for (call_index, (typed_call, legacy_call)) in
            typed_calls.iter().zip(legacy_calls).enumerate()
        {
            assert_eq!(
                typed_call, legacy_call,
                "CallFact parity differs at row {index}, call {call_index}"
            );
        }
        assert_eq!(typed, legacy, "CallFact parity differs at row {index}");
    }
    assert_eq!(output.stats.fact_count, typed.len());
}

#[test]
fn unresolved_native_calls_keep_the_provider_spelling() {
    let span = protocol::Span {
        path: "kernel.cu".to_string(),
        start_line: 2,
        start_column: 4,
        end_line: 2,
        end_column: 18,
    };
    let mut record =
        calls::CallRecord::new("callfact:kernel.cu".to_string(), span.clone(), "cuda");
    record.calls.push(calls::CallSite::new(
        "cudaMalloc".to_string(),
        protocol::Node {
            id: "kernel.cu:2:call".to_string(),
            span,
            kind: "call".to_string(),
            text: "cudaMalloc()".to_string(),
        },
    ));
    let mut legacy = vec![record.clone().into_json()];
    let mut typed = vec![record];
    let resolved = BTreeMap::from([(
        ("kernel.cu".to_string(), 2),
        vec![calls::ResolvedCall {
            qualified_name: "kernel::cudaMalloc".to_string(),
            resolution: graph::Resolution::Unresolved,
            is_external: false,
            is_first_party: false,
            is_standard_library: false,
            is_constructor: false,
        }],
    )]);

    calls::enrich_records(&mut typed, &mut calls::ResolutionIndex::new(&resolved));
    calls::enrich_facts(
        "CallFact",
        &mut legacy,
        &mut calls::ResolutionIndex::new(&resolved),
    );

    assert_eq!(
        (
            typed[0].calls[0].qualified_name.as_str(),
            &legacy[0]["calls"][0]["qualified_name"],
        ),
        ("cudaMalloc", &serde_json::json!("cudaMalloc"))
    );
}

#[test]
fn typed_class_rows_and_the_json_fallback_are_exactly_the_same_facts() {
    let root = python_corpus();
    let mut request = request(root);
    request.families = vec!["ClassFact".to_string()];
    let mut legacy = Vec::new();

    let output = run_session(
        &request,
        &["ClassFact".to_string()],
        |family, mut produced| {
            assert_eq!(family, "ClassFact");
            legacy.append(&mut produced);
            Ok(())
        },
    )
    .expect("the session reads the corpus");
    let typed = output
        .facts
        .classes
        .into_iter()
        .map(classes::ClassRecord::into_json)
        .collect::<Vec<_>>();

    assert_eq!(typed.len(), legacy.len());
    for (index, (typed, legacy)) in typed.iter().zip(&legacy).enumerate() {
        assert_eq!(typed, legacy, "ClassFact parity differs at row {index}");
    }
    assert_eq!(output.stats.fact_count, typed.len());
}

#[test]
fn a_graph_request_refuses_the_fact_stream() {
    let mut request = request(env!("CARGO_MANIFEST_DIR"));
    request.graph = true;

    assert!(run_stream(&request, |_, _| Ok(())).is_err());
}

#[test]
fn a_spooled_family_drains_in_bounded_ordered_batches() {
    let mut spools = FactSpools::new(["CallFact".to_string()]).expect("the spool opens");
    let facts = (0..FACT_BATCH_SIZE * 2 + 1)
        .map(|index| serde_json::json!(index))
        .collect();
    spools.write("CallFact", facts).expect("facts spool");
    let mut batches = Vec::new();

    spools
        .drain("CallFact", |batch| {
            batches.push(batch);
            Ok(())
        })
        .expect("the spool drains");

    assert_eq!(
        batches.iter().map(Vec::len).collect::<Vec<_>>(),
        vec![FACT_BATCH_SIZE, FACT_BATCH_SIZE, 1]
    );
    assert_eq!(batches[0][0], serde_json::json!(0));
    assert_eq!(batches[2][0], serde_json::json!(FACT_BATCH_SIZE * 2));
}

#[test]
fn native_sessions_keep_repository_joins_in_memory() {
    let root = python_corpus();
    let request = Request::analysis(root.to_string(), Vec::new());
    FORBID_FACT_SPOOLS.with(|forbidden| forbidden.set(true));

    let result = run_session_with_generic(
        &request,
        SessionFamilies {
            typed: &["ClassFact".to_string()],
            generic: &["DirectoryFact".to_string(), "TestFunctionFact".to_string()],
        },
        |family, facts| {
            assert!(family.starts_with("@typed:"));
            assert!(facts.is_empty());
            Ok(())
        },
    );
    FORBID_FACT_SPOOLS.with(|forbidden| forbidden.set(false));

    let output = result.expect("the native session completes without a temporary spool");
    assert!(!output.facts.classes.is_empty());
    assert!(output.generic.contains_key("DirectoryFact"));
    assert!(output.generic.contains_key("TestFunctionFact"));
}
