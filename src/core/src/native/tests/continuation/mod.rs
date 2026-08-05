use super::*;
use serde_json::json;

#[test]
fn every_call_a_kernel_makes_is_named_for_the_rules_that_read_them() {
    let facts = facts_for(
        SOURCE,
        RelativePath("src/engine.cu"),
        FactFamily("CallFact"),
    );
    let names: Vec<&str> = facts[0]["calls"]
        .as_array()
        .unwrap()
        .iter()
        .map(|call| call["qualified_name"].as_str().unwrap_or_default())
        .collect();

    assert!(names.contains(&"__syncthreads"));
    assert!(names.contains(&"cudaMemcpy"));
    assert!(names.contains(&"helper"));
    assert_eq!(facts[0]["calls"][0]["node"]["kind"], "call");
    assert_eq!(facts[0]["language"], "cuda");
}

#[test]
fn the_cuda_grammar_reads_a_launch_the_cpp_grammar_cannot_see() {
    let source = "__global__ void scale(float* data) {\n  __shared__ float tile[32];\n}\n\nvoid host(cudaStream_t stream) {\n  scale<<<grid, block>>>(data);\n  scale<<<grid, block, 1024, stream>>>(data);\n}\n";
    let facts = facts_for(
        source,
        RelativePath("src/scale.cu"),
        FactFamily("KernelLaunchFact"),
    );

    assert_eq!(
        json!([
            facts.len(),
            facts[0]["kernel"],
            facts[0]["grid"],
            facts[0]["block"],
            facts[0]["stream"],
            facts[0]["enclosing_function"],
            facts[1]["dynamic_shared_bytes"],
            facts[1]["stream"],
        ]),
        json!([2, "scale", "grid", "block", "", "host", "1024", "stream"])
    );
    assert!(
        facts_for(
            source,
            RelativePath("src/scale.cpp"),
            FactFamily("KernelLaunchFact")
        )
        .is_empty()
    );
}

#[test]
fn a_header_and_the_unit_that_implements_it_declare_one_module() {
    let graph = crate::graph::build(
        "repo",
        &[
            Document {
                relative: "src/engine.cpp".to_string(),
                source: "#include \"engine.h\"\n\nint Engine::run(float value) { return 1; }\n"
                    .to_string(),
            },
            Document {
                relative: "src/engine.h".to_string(),
                source: "class Engine {\n public:\n  int run(float value);\n};\n".to_string(),
            },
        ],
    )
    .expect("the graph builds");
    let modules: Vec<&str> = graph
        .nodes
        .iter()
        .filter(|item| item.kind == NodeKind::Module)
        .map(|item| item.qualname.as_str())
        .collect();

    assert_eq!(modules, vec!["src::engine"]);
    assert!(
        graph
            .nodes
            .iter()
            .any(|item| item.id == "cpp:class:src::engine::Engine")
    );
    assert!(graph.edges.iter().any(|edge| edge.kind == EdgeKind::Define
        && edge.target == "cpp:method:src::engine::Engine::run"));
}

/// Return every comment group one source states, which is what the family carries.
fn groups_for<Path: AsRef<str>>(source: &str, relative: RelativePath<Path>) -> Vec<Value> {
    let facts = facts_for(source, relative, FactFamily("CommentFact"));
    facts[0]["groups"].as_array().cloned().unwrap_or_default()
}

/// Return every kind one tree uses, so a frontend cannot invent one quietly.
fn kinds_used(tree: &Value) -> BTreeSet<String> {
    let mut found = BTreeSet::new();
    let mut pending = vec![tree];
    while let Some(node) = pending.pop() {
        if let Some(kind) = node["kind"].as_str() {
            found.insert(kind.to_string());
        }
        pending.extend(node["children"].as_array().into_iter().flatten());
    }
    found
}

#[test]
fn both_ways_this_language_opens_a_comment_reach_the_family() {
    let groups = groups_for(SOURCE, RelativePath("src/engine.cu"));

    assert!(groups.is_empty(), "this fixture states none");
    let held = groups_for(
        "/* what this unit is */\n\n// what the next line does\nint run() { return 1; }\n",
        RelativePath("src/engine.cpp"),
    );
    let said: Vec<&str> = held
        .iter()
        .map(|group| group["node"]["text"].as_str().unwrap_or_default())
        .collect();

    assert_eq!(
        said,
        vec!["/* what this unit is */", "// what the next line does"]
    );
    assert_eq!(held[0]["token_count"], 6);
}

#[test]
fn commented_out_native_source_is_told_apart_from_prose_about_it() {
    let groups = groups_for(
        concat!(
            "int run(int count) {\n",
            "  // int stale = count * 2;\n",
            "\n",
            "  // retry twice before giving up\n",
            "  return count;\n",
            "}\n",
            "\n",
            "// static int dead(int value) {\n",
            "//   return value + 1;\n",
            "// }\n",
        ),
        RelativePath("src/engine.c"),
    );
    let read: Vec<bool> = groups
        .iter()
        .map(|group| group["parses_as_source"].as_bool().unwrap_or_default())
        .collect();

    // A statement and a whole declaration are both source; the sentence between them is not.
    assert_eq!(read, vec![true, false, true]);
}

#[test]
fn a_tool_switch_is_marked_and_never_absorbed_into_the_prose_beside_it() {
    let groups = groups_for(
        "// NOLINTNEXTLINE(readability)\n// what this really does\nint run() { return 1; }\n",
        RelativePath("src/engine.cpp"),
    );

    assert_eq!(groups.len(), 2);
    assert_eq!(groups[0]["is_directive"], true);
    assert_eq!(groups[0]["parses_as_source"], false);
    assert_eq!(groups[1]["is_directive"], false);
}

#[test]
fn a_comment_marker_inside_a_literal_is_text_rather_than_a_comment() {
    let groups = groups_for(
        "const char* url = \"https://example.com/a//b\";\n// the only note\n",
        RelativePath("src/engine.cpp"),
    );

    assert_eq!(groups.len(), 1);
    assert_eq!(groups[0]["node"]["text"], "// the only note");
}

#[test]
fn a_declaration_carries_its_own_source_and_its_own_tree() {
    let facts = facts_for(
        "int rename(int count) {\n  int bare = count + 1;\n  return bare;\n}\n",
        RelativePath("src/engine.cpp"),
        FactFamily("SyntaxFact"),
    );
    let tree = crate::syntax::unpack(&facts[0]);
    let body = tree["children"].as_array().unwrap();
    let kinds: Vec<&str> = body
        .iter()
        .map(|item| item["kind"].as_str().unwrap_or_default())
        .collect();

    assert_eq!(
        json!([
            facts.len(),
            facts[0]["qualname"],
            facts[0]["kind"],
            facts[0]["language"],
        ]),
        json!([1, "rename", "callable", "cpp"])
    );
    assert!(
        facts[0]["source"]
            .as_str()
            .unwrap_or_default()
            .starts_with("int rename")
    );
    // The stated return type comes first, then the body, in the order the source states it.
    assert_eq!(kinds, vec!["name", "binding", "return"]);
    assert_eq!(body[1]["name"], "bare");
}

#[test]
fn a_type_tree_stops_at_the_members_that_carry_their_own_facts() {
    let facts = facts_for(
        SOURCE,
        RelativePath("src/engine.cu"),
        FactFamily("SyntaxFact"),
    );
    let named: Vec<&str> = facts
        .iter()
        .map(|fact| fact["qualname"].as_str().unwrap_or_default())
        .collect();
    let held = facts
        .iter()
        .find(|fact| fact["qualname"] == "app::Engine")
        .expect("the type carries a fact");

    assert_eq!(
        named,
        vec!["app::Engine", "app::Engine::run", "helper", "scale"]
    );
    let tree = crate::syntax::unpack(held);
    let members = tree["children"].as_array().unwrap();
    let methods: Vec<&Value> = members
        .iter()
        .filter(|item| item["kind"] == "callable")
        .collect();
    assert_eq!(methods.len(), 2);
    assert!(
        methods[0]["children"].as_array().unwrap().is_empty(),
        "a method body inside a type tree would count every defect in it twice"
    );
}

#[test]
fn a_kernel_is_named_by_the_namespace_and_the_type_that_hold_it() {
    let facts = facts_for(
        "namespace app {\nnamespace inner {\nclass Engine {\n public:\n  int run() { return 1; }\n};\n}\n}\n",
        RelativePath("src/engine.cu"),
        FactFamily("SyntaxFact"),
    );
    let named: Vec<&str> = facts
        .iter()
        .map(|fact| fact["qualname"].as_str().unwrap_or_default())
        .collect();

    assert_eq!(named, vec!["app::inner::Engine", "app::inner::Engine::run"]);
}

#[test]
fn the_tree_reaches_the_names_the_calls_and_the_branches_a_body_states() {
    let facts = facts_for(
        concat!(
            "int run(int count) {\n",
            "  int total = 0;\n",
            "  if (count > 0) {\n",
            "    total = helper(count);\n",
            "  }\n",
            "  count;\n",
            "  return total;\n",
            "}\n",
        ),
        RelativePath("src/engine.cpp"),
        FactFamily("SyntaxFact"),
    );
    let mut seen = Vec::new();
    let tree = crate::syntax::unpack(&facts[0]);
    let mut pending = vec![&tree];
    while let Some(node) = pending.pop() {
        seen.push((
            node["kind"].as_str().unwrap_or_default().to_string(),
            node["name"].as_str().unwrap_or_default().to_string(),
        ));
        pending.extend(node["children"].as_array().into_iter().flatten());
    }

    assert!(seen.contains(&("call".to_string(), "helper".to_string())));
    assert!(seen.contains(&("binding".to_string(), "total".to_string())));
    assert!(seen.contains(&("branch".to_string(), String::new())));
    assert!(seen.contains(&("return".to_string(), String::new())));
}

#[test]
fn a_statement_that_only_produces_a_value_is_located_at_that_value() {
    let facts = facts_for(
        "int run(int count) {\n  count;\n  return count;\n}\n",
        RelativePath("src/engine.cpp"),
        FactFamily("SyntaxFact"),
    );
    let tree = crate::syntax::unpack(&facts[0]);
    let body = tree["children"].as_array().unwrap();
    let effect = body
        .iter()
        .find(|item| item["kind"] == "effect")
        .expect("a bare expression is an effect");

    // The rule finding a useless statement matches the child covering the statement exactly,
    // so the semicolon has to stay out of the effect's own span.
    assert_eq!(effect["span"], effect["children"][0]["span"]);
    assert_eq!(effect["children"][0]["kind"], "name");
}

#[test]
fn a_comment_is_never_a_node_of_the_code_around_it() {
    let facts = facts_for(
        "int run() {\n  // a note between statements\n  return 1;\n}\n",
        RelativePath("src/engine.cpp"),
        FactFamily("SyntaxFact"),
    );
    let tree = crate::syntax::unpack(&facts[0]);
    let said: Vec<&str> = tree["children"]
        .as_array()
        .unwrap()
        .iter()
        .map(|item| item["kind"].as_str().unwrap_or_default())
        .collect();

    assert_eq!(said, vec!["name", "return"]);
}

#[test]
fn every_kind_a_tree_uses_is_in_the_shared_vocabulary() {
    let facts = facts_for(
        SOURCE,
        RelativePath("src/engine.cu"),
        FactFamily("SyntaxFact"),
    );
    let known: BTreeSet<&str> = crate::syntax::KINDS.iter().copied().collect();

    assert!(!facts.is_empty());
    for fact in &facts {
        for kind in kinds_used(&crate::syntax::unpack(fact)) {
            assert!(
                known.contains(kind.as_str()),
                "{kind} is not in the vocabulary"
            );
        }
    }
}

#[test]
fn a_parameter_binds_by_position_and_says_when_a_caller_may_leave_it_out() {
    let graph = crate::graph::build(
        "repo",
        &[Document {
            relative: "src/engine.cpp".to_string(),
            source: concat!(
                "template <typename... Rest>\n",
                "int run(int value, float scale = 1.0, Rest&&... rest) { return value; }\n"
            )
            .to_string(),
        }],
    )
    .expect("the graph builds");
    let stated: Vec<(&str, Option<ParameterKind>, bool)> = graph
        .nodes
        .iter()
        .filter(|item| item.kind == NodeKind::Parameter)
        .map(|item| {
            (
                item.qualname.as_str(),
                item.parameter_kind,
                item.has_default,
            )
        })
        .collect();

    assert_eq!(
        stated,
        vec![
            ("run::rest", Some(ParameterKind::VarPositional), false),
            ("run::scale", Some(ParameterKind::PositionalOnly), true),
            ("run::value", Some(ParameterKind::PositionalOnly), false),
        ]
    );
}
