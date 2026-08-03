use super::*;

#[test]
fn a_super_path_beyond_the_crate_root_stays_unresolved() {
    let graph = crate::graph::build(
        "repo",
        &[
            Document {
                relative: "kernel/src/lib.rs".to_string(),
                source: "use super::builder;\n".to_string(),
            },
            Document {
                relative: "kernel/src/builder.rs".to_string(),
                source: "pub fn build() {}\n".to_string(),
            },
        ],
    )
    .expect("the graph builds");

    assert!(
        graph
            .nodes
            .iter()
            .any(|node| node.kind == NodeKind::UnresolvedSymbol
                && node.qualname == "kernel::super::builder")
    );
}

#[test]
fn a_nested_module_climbs_from_itself_rather_than_from_the_file_around_it() {
    let graph = graph_of(
        "pub fn build() -> usize {\n    1\n}\n\n#[cfg(test)]\nmod tests {\n    use super::*;\n\n    #[test]\n    fn it_builds() {\n        assert_eq!(build(), 1);\n    }\n}\n",
    );
    let reached: Vec<&str> = graph
        .edges
        .iter()
        .filter(|edge| edge.kind == EdgeKind::Import)
        .map(|edge| edge.target.as_str())
        .collect();

    assert_eq!(reached, ["rust:module:kernel::engine"]);
}

#[test]
fn importing_a_module_by_name_reaches_that_module_and_not_the_one_holding_it() {
    let graph = crate::graph::build(
        "repo",
        &[
            Document {
                relative: "kernel/src/main.rs".to_string(),
                source: "mod codec;\nmod engine;\n".to_string(),
            },
            Document {
                relative: "kernel/src/codec.rs".to_string(),
                source: "pub struct Frame;\n".to_string(),
            },
            Document {
                relative: "kernel/src/engine.rs".to_string(),
                source:
                    "use crate::codec;\n\npub fn build() -> codec::Frame {\n    codec::Frame\n}\n"
                        .to_string(),
            },
        ],
    )
    .expect("the graph builds");
    let reached: Vec<&str> = graph
        .edges
        .iter()
        .filter(|edge| edge.kind == EdgeKind::Import)
        .map(|edge| edge.target.as_str())
        .collect();

    assert_eq!(reached, ["rust:module:kernel::codec"]);
}

/// Return every comment group one source states, which is what the family carries.
fn groups_for(source: &str) -> Vec<Value> {
    let facts = facts_for(source, FactFamily("CommentFact"));
    facts[0]["groups"].as_array().cloned().unwrap_or_default()
}

#[test]
fn every_way_this_language_opens_a_comment_reaches_the_family() {
    let groups = groups_for(concat!(
        "//! what this module is\n",
        "\n",
        "/// what this function does\n",
        "fn run() -> usize {\n",
        "    /* a held note */\n",
        "    1\n",
        "}\n",
    ));
    let said: Vec<&str> = groups
        .iter()
        .map(|group| group["node"]["text"].as_str().unwrap_or_default())
        .collect();

    assert_eq!(
        said,
        vec![
            "//! what this module is",
            "/// what this function does",
            "/* a held note */"
        ]
    );
    assert_eq!(groups[0]["line_count"], 1);
    assert_eq!(groups[0]["token_count"], 5);
    assert_eq!(groups[0]["character_count"], 23);
}

#[test]
fn commented_out_rust_is_told_apart_from_prose_about_it() {
    let groups = groups_for(concat!(
        "fn run(path: &str) -> usize {\n",
        "    // let stale = read(path);\n",
        "    // let parsed = parse(stale);\n",
        "\n",
        "    // retry twice before giving up\n",
        "    path.len()\n",
        "}\n",
        "\n",
        "// fn dead(value: usize) -> usize {\n",
        "//     value + 1\n",
        "// }\n",
    ));
    let read: Vec<(bool, i64)> = groups
        .iter()
        .map(|group| {
            (
                group["parses_as_source"].as_bool().unwrap_or_default(),
                group["line_count"].as_i64().unwrap_or_default(),
            )
        })
        .collect();

    // Statements and a whole declaration are both source; the sentence between them is not.
    assert_eq!(read, vec![(true, 2), (false, 1), (true, 3)]);
}

#[test]
fn a_comment_marker_inside_a_literal_is_text_rather_than_a_comment() {
    let groups = groups_for(concat!(
        "fn run() -> usize {\n",
        "    let url = \"https://example.com/a//b\";\n",
        "    let held = 'x';\n",
        "    let raw = r#\"a /* still text */ b\"#;\n",
        "    /* the only note /* and the one it nests */ here */\n",
        "    url.len() + held.len_utf8() + raw.len()\n",
        "}\n",
    ));

    assert_eq!(groups.len(), 1);
    assert_eq!(
        groups[0]["node"]["text"],
        "/* the only note /* and the one it nests */ here */"
    );
}

/// A source is a `str`, so the scanner has to step characters rather than bytes.
///
/// A cursor advancing one byte at a time lands inside any character wider than ASCII, and the
/// next slice off it panics and takes the whole run down. Every place a wide character can be
/// written is here at once, since each of them reaches the scanner through a different arm.
#[test]
fn a_source_written_outside_ascii_is_read_rather_than_crashed_on() {
    let groups = groups_for(concat!(
        "/* la mesa está aquí */\n",
        "fn café(entrée: &str) -> usize {\n",
        "    let señal = 'é';\n",
        "    let frase = \"até logo\";\n",
        "    // la señal está aquí\n",
        "    entrée.len() + frase.len() + señal.len_utf8()\n",
        "}\n",
    ));
    let said: Vec<&str> = groups
        .iter()
        .map(|group| group["node"]["text"].as_str().unwrap_or_default())
        .collect();

    assert_eq!(
        said,
        vec!["/* la mesa está aquí */", "// la señal está aquí"]
    );
}

/// A string that both escapes a quote and holds wide characters stays one literal.
#[test]
fn an_escaped_quote_beside_a_wide_character_never_swallows_the_comment_after_it() {
    let groups = groups_for(concat!(
        "fn run() -> usize {\n",
        "    let held = \"até \\\"logo\\\" // não\";\n",
        "    // the only note in this file\n",
        "    held.len()\n",
        "}\n",
    ));

    assert_eq!(groups.len(), 1);
    assert_eq!(groups[0]["node"]["text"], "// the only note in this file");
}

/// A lifetime and a character literal open the same way and close differently.
#[test]
fn a_lifetime_is_stepped_past_where_a_character_literal_is_read_to_its_close() {
    let groups = groups_for(concat!(
        "fn head<'a>(text: &'a str) -> &'a str {\n",
        "    let marker = '/';\n",
        "    let wide = '中';\n",
        "    let escaped = '\\u{1F600}';\n",
        "    // the only note in this file\n",
        "    text\n",
        "}\n",
    ));

    assert_eq!(groups.len(), 1);
    assert_eq!(groups[0]["node"]["text"], "// the only note in this file");
}

#[test]
fn a_tool_switch_is_marked_and_never_absorbed_into_the_prose_beside_it() {
    let groups = groups_for("// rustfmt::skip\n// what this really does\nfn run() {}\n");

    assert_eq!(groups.len(), 2);
    assert_eq!(groups[0]["is_directive"], true);
    assert_eq!(groups[0]["parses_as_source"], false);
    assert_eq!(groups[1]["is_directive"], false);
}

#[test]
fn a_work_marker_survives_into_the_text_the_general_rule_reads() {
    let groups = groups_for(concat!(
        "// TODO: handle the empty case\n",
        "fn load(path: &str) -> usize {\n",
        "    path.len() // FIXME: this loses the encoding\n",
        "}\n",
    ));
    let said: String = groups
        .iter()
        .map(|group| group["node"]["text"].as_str().unwrap_or_default())
        .collect();

    assert!(said.contains("TODO"));
    assert!(said.contains("FIXME"));
}

/// The shared vocabulary, the depth arithmetic, and the chain rule, all at once.
///
/// The same program written for the reference frontend has to produce the same records, since
/// the complexity and nesting rules own one scoring model for every language. What this
/// language spells differently is only where the structure lives: a `match` bound to a name is
/// a structure and a closure is a callable of its own.
#[test]
fn control_increments_record_their_nesting_depth() {
    let facts = facts_for(
        concat!(
            "pub fn run(items: Vec<Vec<usize>>) -> usize {\n",
            "    for item in items {\n",
            "        if item.is_empty() {\n",
            "            return 0;\n",
            "        } else if item.len() > 2 {\n",
            "            return 1;\n",
            "        } else {\n",
            "            return 2;\n",
            "        }\n",
            "    }\n",
            "    let picked = match 0 {\n",
            "        0 => 0,\n",
            "        _ => 1,\n",
            "    };\n",
            "    let held = |value: usize| if value > 0 { 1 } else { 0 };\n",
            "    picked + held(1)\n",
            "}\n",
        ),
        FactFamily("FunctionFact"),
    );
    let increments: Vec<(&str, i64)> = facts[0]["control_increments"]
        .as_array()
        .unwrap()
        .iter()
        .map(|held| {
            (
                held["kind"].as_str().unwrap_or_default(),
                held["nesting_depth"].as_i64().unwrap_or_default(),
            )
        })
        .collect();

    assert_eq!(
        increments,
        vec![
            ("loop", 0),
            ("conditional", 1),
            ("alternative", 1),
            ("alternative", 1),
            ("switch", 0),
        ]
    );
    assert_eq!(facts[0]["conditional_count"], 1);
    assert_eq!(facts[0]["implementation_lines"], 15);
}

#[test]
fn a_call_says_whether_anything_took_its_result() {
    let facts = facts_for(
        concat!(
            "pub fn run(values: Vec<usize>) -> usize {\n",
            "    record(values.len());\n",
            "    let total = sum(&values);\n",
            "    total\n",
            "}\n",
        ),
        FactFamily("CallFact"),
    );
    let called: Vec<(&str, bool)> = facts[0]["calls"]
        .as_array()
        .unwrap()
        .iter()
        .map(|call| {
            (
                call["qualified_name"].as_str().unwrap_or_default(),
                call["result_is_discarded"].as_bool().unwrap_or_default(),
            )
        })
        .collect();

    assert_eq!(
        called,
        vec![("record", true), ("len", false), ("sum", false)]
    );
    assert_eq!(facts[0]["calls"][0]["node"]["text"], "record(values.len())");
    assert_eq!(facts[0]["module_bindings"][0], "run");
}
