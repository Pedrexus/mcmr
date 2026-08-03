use super::*;
use crate::graph::{EdgeKind, NodeKind, ParameterKind};
use serde_json::json;
use std::collections::BTreeSet;

const SOURCE: &str = "#include <cuda_runtime.h>\n#include \"engine.h\"\n\nnamespace app {\n\nclass Engine : public Base {\n public:\n  Engine();\n  int run(float value);\n private:\n  int limit;\n};\n\nint Engine::run(float value) {\n  return helper(value);\n}\n\n}\n\nstatic int helper(int amount) { return amount; }\n\n__global__ void scale(float* data) {\n  __syncthreads();\n  cudaMemcpy(data, data, 4, cudaMemcpyHostToDevice);\n}\n";

#[derive(Clone, Copy)]
struct FactFamily<'a>(&'a str);

#[derive(Clone, Copy)]
struct RelativePath<'a>(&'a str);

fn facts_for(source: &str, relative: RelativePath<'_>, family: FactFamily<'_>) -> Vec<Value> {
    let document = Document {
        relative: relative.0.to_string(),
        source: source.to_string(),
    };
    let mut facts = BTreeMap::from([(family.0.to_string(), Vec::new())]);
    extract(&document, &mut facts, &mut Stats::default());
    facts.remove(family.0).unwrap_or_default()
}

/// Return each parameter of the one function a source states, as name and declared type.
fn signature_of(source: &str) -> Vec<(String, String)> {
    facts_for(
        source,
        RelativePath("src/engine.cu"),
        FactFamily("FunctionFact"),
    )[0]["parameters"]
        .as_array()
        .expect("a parameter list")
        .iter()
        .map(|item| {
            (
                item["name"].as_str().unwrap_or_default().to_string(),
                item["type_name"].as_str().unwrap_or_default().to_string(),
            )
        })
        .collect()
}

#[test]
fn a_parameter_carries_the_type_a_caller_sees_rather_than_the_word_beside_it() {
    let stated = signature_of(concat!(
        "__global__ void merge(int32_t *__restrict__ tokens, int32_t seg_start,\n",
        "                      const int32_t *counts, int32_t &out, float const *weights,\n",
        "                      const int limit, int *const fixed) {}\n"
    ));

    assert_eq!(
        stated,
        vec![
            ("tokens".to_string(), "int32_t *".to_string()),
            ("seg_start".to_string(), "int32_t".to_string()),
            ("counts".to_string(), "const int32_t *".to_string()),
            ("out".to_string(), "int32_t &".to_string()),
            // `float const *` and `const float *` are one type spelled two ways, so both
            // arrive as one string or a rule comparing them misses a real pair.
            ("weights".to_string(), "const float *".to_string()),
            // A qualifier sharing the level that binds the name is one no caller observes,
            // so neither of these is separated from a plain `int` or a plain `int *`.
            ("limit".to_string(), "int".to_string()),
            ("fixed".to_string(), "int *".to_string()),
        ]
    );
}

#[test]
fn two_positions_a_caller_cannot_transpose_never_read_as_one_type() {
    let stated = signature_of(concat!(
        "__global__ void probe(int **flat, int *const *deep, char buf[8], char other[16],\n",
        "                      void (*hook)(int), void (*report)(float),\n",
        "                      int (&grid)[4], int (&block)[8], float &&moved) {}\n"
    ));
    let held: Vec<&str> = stated.iter().map(|(_, kind)| kind.as_str()).collect();

    assert_eq!(
        held,
        vec![
            "int * *",
            "int * const *",
            "char [8]",
            "char [16]",
            "void (int) *",
            "void (float) *",
            "int [4] &",
            "int [8] &",
            "float &&",
        ]
    );
    assert_eq!(held.len(), held.iter().collect::<BTreeSet<_>>().len());
}

#[test]
fn a_position_a_caller_may_leave_out_is_still_a_position() {
    let stated = signature_of("__global__ void run(int value, float scale = 1.0f) {}\n");
    let required: Vec<bool> = facts_for(
        "__global__ void run(int value, float scale = 1.0f) {}\n",
        RelativePath("src/engine.cu"),
        FactFamily("FunctionFact"),
    )[0]["parameters"]
        .as_array()
        .expect("a parameter list")
        .iter()
        .map(|item| item["is_required_by_external_contract"] == true)
        .collect();

    // Dropping the optional one closed the gap between two parameters that never sit side by
    // side, so a rule about transposable neighbours compared a pair no caller can write.
    assert_eq!(stated.len(), 2);
    assert_eq!(stated[1].0, "scale");
    assert_eq!(required, vec![true, false]);
}

#[test]
fn native_boolean_parameters_keep_their_positional_contract() {
    let parameters = facts_for(
        "void render(bool inline, _Bool strict, int count) {}\n",
        RelativePath("src/render.cpp"),
        FactFamily("FunctionFact"),
    )[0]["parameters"]
        .as_array()
        .expect("a parameter list")
        .clone();

    assert_eq!(parameters[0]["has_boolean_annotation"], true);
    assert_eq!(parameters[1]["has_boolean_annotation"], true);
    assert_eq!(parameters[2]["has_boolean_annotation"], false);
    assert!(
        parameters
            .iter()
            .all(|parameter| parameter["is_positional_only"] == true)
    );
}

#[test]
fn native_function_measurements_cover_the_body_without_its_comments_or_signature() {
    let facts = facts_for(
        concat!(
            "task<int> fetch() {\n",
            "  // Explain why readiness is awaited.\n",
            "  co_await ready();\n",
            "  co_return 1;\n",
            "}\n",
        ),
        RelativePath("src/fetch.cpp"),
        FactFamily("FunctionFact"),
    );

    assert_eq!(facts[0]["is_async"], true);
    assert_eq!(facts[0]["implementation_lines"], 2);
    assert_eq!(facts[0]["direct_statement_count"], 2);
    assert_eq!(
        facts[0]["definition"]["text"],
        concat!(
            "task<int> fetch() {\n",
            "  // Explain why readiness is awaited.\n",
            "  co_await ready();\n",
            "  co_return 1;\n",
            "}"
        )
    );
}

#[test]
fn a_call_through_a_receiver_keeps_the_receiver_the_source_wrote() {
    let facts = facts_for(
        concat!(
            "void bench(nvbench::state& state) {\n",
            "  state.exec(timer);\n",
            "  self->read(name);\n",
            "  helper(name);\n",
            "  cuda::std::move(name);\n",
            "}\n"
        ),
        RelativePath("src/engine.cu"),
        FactFamily("CallFact"),
    );
    let named: Vec<&str> = facts[0]["calls"]
        .as_array()
        .expect("a call list")
        .iter()
        .map(|call| call["qualified_name"].as_str().unwrap_or_default())
        .collect();

    // `exec` alone reads as the scope builtin several languages spell that way, and every
    // general rule matching a builtin by name then answers yes for any object holding one.
    assert_eq!(
        named,
        vec!["state.exec", "self.read", "helper", "cuda::std::move"]
    );
}

#[test]
fn a_native_call_credits_the_declaration_it_reaches() {
    let graph = crate::graph::build(
        "repo",
        &[Document {
            relative: "beta.cpp".to_string(),
            source: concat!(
                "int beta(int value) { return value + 2; }\n",
                "int caller(int value) { return beta(value); }\n"
            )
            .to_string(),
        }],
    )
    .expect("the graph builds");
    let reached = crate::graph::reach(&graph);
    let declarations = &reached[0].declarations;
    let beta = declarations
        .iter()
        .find(|declared| declared.qualname.ends_with("::beta"))
        .expect("the called declaration");

    assert_eq!(beta.references.own_file_references, 1);
    assert_eq!(beta.uses.call_count, 1);
}

#[test]
fn an_external_symbol_keeps_the_name_the_source_qualified() {
    let graph = crate::graph::build(
        "repo",
        &[Document {
            relative: "unit.cpp".to_string(),
            source: "int run(const char* left, const char* right) { return std::strcmp(left, right); }\n"
                .to_string(),
        }],
    )
    .expect("the graph builds");

    assert!(
        graph
            .nodes
            .iter()
            .any(|node| node.qualname == "std::strcmp")
    );
    assert!(
        !graph
            .nodes
            .iter()
            .any(|node| node.qualname == "std::std::strcmp")
    );
}

#[test]
fn control_increments_record_their_nesting_depth() {
    let source = concat!(
        "int score(int value) {\n",
        "  if (value > 0) {\n",
        "    for (int i = 0; i < value; ++i) {\n",
        "      while (value > i) { value--; }\n",
        "    }\n",
        "  } else if (value < 0) {\n",
        "    value = 0;\n",
        "  } else {\n",
        "    value = 1;\n",
        "  }\n",
        "  return value;\n",
        "}\n"
    );
    let facts = facts_for(
        source,
        RelativePath("src/score.cpp"),
        FactFamily("FunctionFact"),
    );
    let increments: Vec<(&str, i64)> = facts[0]["control_increments"]
        .as_array()
        .expect("control increments")
        .iter()
        .map(|item| {
            (
                item["kind"].as_str().unwrap_or_default(),
                item["nesting_depth"].as_i64().unwrap_or_default(),
            )
        })
        .collect();

    assert_eq!(
        increments,
        vec![
            ("conditional", 0),
            ("loop", 1),
            ("loop", 2),
            ("alternative", 0),
            ("alternative", 0),
        ]
    );
    assert_eq!(facts[0]["conditional_count"], 1);
}

#[test]
fn a_launch_says_whether_its_own_unit_meets_a_stream_at_all() {
    let alone = facts_for(
        "void run(float* data) {\n  scale<<<grid, block>>>(data);\n}\n",
        RelativePath("src/engine.cu"),
        FactFamily("KernelLaunchFact"),
    );
    let overlapped = facts_for(
        concat!(
            "void run(cudaStream_t stream, float* data) {\n",
            "  scale<<<grid, block>>>(data);\n",
            "}\n"
        ),
        RelativePath("src/engine.cu"),
        FactFamily("KernelLaunchFact"),
    );

    // A default-stream launch drains an overlap only where there is one, and whether there is
    // one is a question about the whole translation unit rather than about the launch.
    assert_eq!(alone[0]["unit_uses_streams"], false);
    assert_eq!(overlapped[0]["unit_uses_streams"], true);
}

#[test]
fn an_access_specifier_is_what_visibility_means_in_this_language() {
    let facts = facts_for(
        SOURCE,
        RelativePath("src/engine.cu"),
        FactFamily("ClassFact"),
    );
    let classes = facts[0]["classes"].as_array().unwrap();
    let methods = classes[0]["methods"].as_array().unwrap();

    assert_eq!(
        json!([
            classes[0]["name"],
            classes[0]["direct_bases"][0],
            classes[0]["field_count"],
            methods[0]["kind"],
            methods[0]["visibility"],
            methods[1]["name"],
            methods[1]["visibility"],
        ]),
        json!([
            "Engine",
            "Base",
            1,
            "constructor",
            "public",
            "run",
            "public"
        ])
    );
    assert!(
        classes[0]["source"]
            .as_str()
            .is_some_and(|source| source.contains("class Engine"))
    );
    assert!(
        methods[0]["source"]
            .as_str()
            .is_some_and(|source| source.contains("Engine()"))
    );
}

#[test]
fn static_is_how_this_language_narrows_a_free_function() {
    let facts = facts_for(
        SOURCE,
        RelativePath("src/engine.cu"),
        FactFamily("FunctionFact"),
    );
    let named: BTreeMap<&str, &Value> = facts
        .iter()
        .map(|fact| (fact["name"].as_str().unwrap_or_default(), fact))
        .collect();

    assert_eq!(named["helper"]["visibility"], "internal");
    assert_eq!(named["scale"]["visibility"], "public");
    assert_eq!(named["Engine::run"]["scope"], "method");
}

#[test]
fn an_include_records_whether_it_stays_inside_the_project() {
    let facts = facts_for(
        SOURCE,
        RelativePath("src/engine.cu"),
        FactFamily("ImportBindingFact"),
    );

    assert_eq!(facts[0]["module"], "cuda_runtime.h");
    assert_eq!(facts[0]["is_external"], true);
    assert_eq!(facts[1]["module"], "engine.h");
    assert_eq!(facts[1]["is_project_owned"], true);
}

#[test]
fn an_include_beyond_the_repository_root_keeps_its_unresolved_climb() {
    assert_eq!(
        HeaderPath {
            including: "src/main.cpp",
            written: "../../engine.h",
        }
        .module(),
        "..::engine"
    );
}

mod continuation;
