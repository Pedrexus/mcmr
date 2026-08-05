use super::*;

#[test]
fn executable_macro_bodies_still_contribute_clone_tokens() {
    let wrapped = |name: &str, total: &str, item: &str| {
        let body = rust_body(name, total, item);
        body.replacen('{', "{\n    execute! {", 1)
            .replacen("\n}\n", "\n    }\n}\n", 1)
    };

    let facts = scan(&[
        document("left.rs", wrapped("total_over", "total", "row")),
        document("right.rs", wrapped("sum_above", "carried", "item")),
    ]);

    assert_eq!(paths(&facts), vec![vec!["left.rs", "right.rs"]]);
}

#[test]
fn a_rust_doc_comment_never_makes_two_items_copies_of_each_other() {
    let commented = |explanation: &str| {
        format!(
            "/// {explanation}\n/// {explanation}\n/// {explanation}\n/// {explanation}\n/// \
             {explanation}\n/// {explanation}\n/// {explanation}\n/// {explanation}\npub const \
             LIMIT: i64 = 3;\n"
        )
    };

    let facts = scan(&[
        document("left.rs", commented("one explanation")),
        document("right.rs", commented("another explanation entirely")),
    ]);

    assert!(facts.is_empty());
}

#[test]
fn a_comment_and_a_spacing_choice_never_decide_whether_two_bodies_are_copies() {
    let plain = body("total_over", "total", "row");
    let dressed = format!(
        "# an explanation the other copy never wrote down\n{}",
        body("total_over", "total", "row").replace(" = 0", "  =  0")
    );

    let facts = scan(&[document("left.py", &plain), document("right.py", &dressed)]);

    assert_eq!(paths(&facts), vec![vec!["left.py", "right.py"]]);
}

#[test]
fn a_file_this_kernel_has_no_reader_for_is_skipped() {
    let facts = scan(&[
        document("notes.md", "the same sentence twice"),
        document("other.md", "the same sentence twice"),
    ]);

    assert!(facts.is_empty());
}

#[test]
fn a_file_that_does_not_parse_contributes_nothing_rather_than_failing() {
    let broken = "def totals(:::\n";

    assert!(scan(&[document("a.py", broken), document("b.py", broken)]).is_empty());
    assert!(scan(&[document("a.rs", broken), document("b.rs", broken)]).is_empty());
}

#[test]
fn malformed_brace_source_cannot_contribute_partial_clone_evidence() {
    let malformed = [
        "} function run() {}",
        "function run() {",
        "function run() { /* unfinished",
        "function run() { const value = \"unfinished",
        "function run() { const value = \\",
    ];

    for source in malformed {
        assert!(Stream::read(&document("a.ts", source), &mut Alphabet::default()).is_none());
    }
}

#[test]
fn the_brace_reader_drops_comments_and_flattens_every_literal() {
    let mut alphabet = Alphabet::default();
    let source = "/* gone\n   also gone */\nconst a = \"text\"; // gone\nconst b = 0x1f;\n\
                  const c = true;\nconst d = null;\n";

    let tokens = braces(&document("a.ts", source), &mut alphabet)
        .expect("the complete source has a complete token stream");
    let written: Vec<String> = tokens
        .iter()
        .map(|token| {
            alphabet
                .text(token.symbol)
                .map(str::to_owned)
                .expect("interned")
        })
        .collect();

    assert_eq!(
        written,
        [
            "const", IDENTIFIER, "=", TEXT, ";", "const", IDENTIFIER, "=", NUMBER, ";", "const",
            IDENTIFIER, "=", TRUTH, ";", "const", IDENTIFIER, "=", NOTHING, ";",
        ]
    );
    assert_eq!(tokens[0].line, 3);
    assert_eq!(tokens[5].line, 4);
}

#[test]
fn a_body_pasted_twice_into_one_file_is_a_clone_of_itself() {
    let twice = format!(
        "{}\n\ndef unrelated(rows):\n    return len(rows)\n\n\n{}",
        body("total_over", "total", "row"),
        body("sum_above", "carried", "item")
    );

    let facts = scan(&[document("a.py", &twice)]);

    assert_eq!(paths(&facts), vec![vec!["a.py", "a.py"]]);
    let fragments = facts[0]["fragments"].as_array().expect("fragments");
    let first = fragments[0]["end_line"].as_u64().expect("end");
    let second = fragments[1]["start_line"].as_u64().expect("start");
    assert!(second > first, "{second} overlaps a copy ending at {first}");
}

#[test]
fn one_clone_window_cannot_cross_between_python_methods() {
    let source = "class EditRows:\n    def edit(self, rows):\n        index = rows[0][0]\n        return Edit(\n            plan=FixPlan(\n                summary=value(self.rewrites, index, \"summary\"),\n                rewrites=[rewrite for _, rewrite in rows],\n            ),\n            safety=Safety(value(self.rewrites, index, \"safety\")),\n        )\n\n    def inline(self, index, nodes, imports):\n        return Inline(\n            declaration=nodes[\"declaration\"][0],\n            body=nodes[\"body\"][0],\n            references=list(nodes.get(\"reference\", [])),\n        )\n\n    def move(self, index, nodes, imports):\n        return Move(\n            target=nodes[\"target\"][0],\n            anchor=nodes[\"anchor\"][0],\n            placement=Placement(value(self.rewrites, index, \"placement\")),\n        )\n\n    def remove(self, index, nodes, imports):\n        return Remove(target=nodes[\"target\"][0])\n";

    let facts = scan(&[document("materializer.py", source)]);

    assert!(facts.iter().all(|fact| {
        fact["fragments"]
            .as_array()
            .expect("fragments")
            .iter()
            .all(|fragment| {
                !fragment["source"]
                    .as_str()
                    .unwrap_or_default()
                    .contains("\n    def ")
            })
    }));
}

#[test]
fn a_self_similar_run_never_reports_a_copy_that_overlaps_another() {
    let source = format!("def repeated():\n{}", "    run(a, b)\n".repeat(40));
    let facts = scan(&[document("a.py", &source)]);

    assert!(!facts.is_empty());
    for fact in &facts {
        let mut covered = 0;
        for fragment in fact["fragments"].as_array().expect("fragments") {
            let start = fragment["start_line"].as_u64().expect("start");
            assert!(
                start > covered,
                "{start} overlaps a copy ending at {covered}"
            );
            covered = fragment["end_line"].as_u64().expect("end");
        }
    }
}

#[test]
fn repeated_token_runs_on_one_physical_line_are_not_independent_copies() {
    let calls = "run(a, b, c, d, e, f, g, h); ".repeat(20);
    let source = format!("function repeated() {{ {calls} }}\n");

    assert!(scan(&[document("a.ts", &source)]).is_empty());
}

#[test]
fn matching_top_level_scaffolding_is_not_an_implementation_clone() {
    let values = (0..80)
        .map(|index| format!("name_{index}"))
        .collect::<Vec<_>>()
        .join(", ");
    let left = format!("VALUES = [{values}]\n");
    let right = format!("OPTIONS = [{values}]\n");

    assert!(scan(&[document("left.py", &left), document("right.py", &right)]).is_empty());
}

#[test]
fn matching_rust_declarations_are_not_implementation_clones() {
    let fields = (0..40)
        .map(|index| format!("    field_{index}: Option<String>,\n"))
        .collect::<String>();
    let left = format!("struct Left {{\n{fields}}}\n");
    let right = format!("struct Right {{\n{fields}}}\n");

    assert!(scan(&[document("left.rs", &left), document("right.rs", &right)]).is_empty());
}

#[test]
fn matching_rust_constant_tables_are_not_implementation_clones() {
    let entries = (0..80)
        .map(|index| format!("    \"entry_{index}\",\n"))
        .collect::<String>();
    let left = format!("fn left() {{\n    const LEFT: &[&str] = &[\n{entries}    ];\n}}\n");
    let right = format!("fn right() {{\n    const RIGHT: &[&str] = &[\n{entries}    ];\n}}\n");

    assert!(scan(&[document("left.rs", &left), document("right.rs", &right)]).is_empty());
}

#[test]
fn literal_concat_fixtures_are_data_rather_than_implementation_clones() {
    let entries = (0..80)
        .map(|index| format!("        \"entry_{index}\\n\",\n"))
        .collect::<String>();
    let left = format!("fn left() {{\n    let source = concat!(\n{entries}    );\n}}\n");
    let right = format!("fn right() {{\n    let fixture = concat!(\n{entries}    );\n}}\n");

    assert!(scan(&[document("left.rs", &left), document("right.rs", &right)]).is_empty());
}
