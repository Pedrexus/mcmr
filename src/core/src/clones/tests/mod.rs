use super::*;

fn document(relative: &str, source: &str) -> Document {
    Document {
        relative: relative.to_string(),
        source: source.to_string(),
    }
}

/// One body long enough to clear the window, written with whatever names it is given.
fn body(name: &str, total: &str, item: &str) -> String {
    format!(
        "def {name}(rows, limit):\n    {total} = 0\n    for {item} in rows:\n        if \
             {item} > limit:\n            {total} = {total} + {item} * 2\n        else:\n          \
             {total} = {total} - 1\n    if {total} < 0:\n        return 0\n    return {total}\n"
    )
}

/// The same body again, written the way a brace language writes it.
fn brace_body(name: &str, total: &str, item: &str) -> String {
    format!(
        "export function {name}(rows: Row[], limit: number): number {{\n  let {total} = 0;\n  \
             for (const {item} of rows) {{\n    if ({item}.value > limit) {{\n      {total} = \
             {total} + {item}.value * 2;\n    }} else {{\n      {total} = {total} - 1;\n    }}\n  \
             }}\n  if ({total} < 0) {{\n    return 0;\n  }}\n  return {total};\n}}\n"
    )
}

/// The same body once more, written the way Rust writes it.
fn rust_body(name: &str, total: &str, item: &str) -> String {
    format!(
        "fn {name}(rows: &[Row], limit: i64) -> i64 {{\n    let mut {total} = 0;\n    for \
             {item} in rows {{\n        if {item}.value > limit {{\n            {total} = {total} \
             + {item}.value * 2;\n        }} else {{\n            {total} = {total} - 1;\n        \
             }}\n    }}\n    if {total} < 0 {{\n        return 0;\n    }}\n    {total}\n}}\n"
    )
}

fn paths(facts: &[Value]) -> Vec<Vec<String>> {
    facts
        .iter()
        .map(|fact| {
            fact["fragments"]
                .as_array()
                .expect("fragments")
                .iter()
                .map(|fragment| fragment["path"].as_str().unwrap_or_default().to_string())
                .collect()
        })
        .collect()
}

#[test]
fn a_copy_whose_locals_were_renamed_is_still_one_clone() {
    let facts = scan(&[
        document("left.py", &body("total_over", "total", "row")),
        document("right.py", &body("sum_above", "carried", "item")),
    ]);

    assert_eq!(paths(&facts), vec![vec!["left.py", "right.py"]]);
    assert_eq!(facts[0]["fragments"][0]["start_line"], 1);
    assert_eq!(facts[0]["fragments"][0]["end_line"], 10);
    assert_eq!(facts[0]["language"], "python");
}

#[test]
fn repeated_polars_query_grammar_is_not_an_implementation_clone() {
    let query = |name: &str, field: &str| {
        format!(
            "import polars as pl\n\ndef {name}(frame):\n    return (\n        \
                 pl.when(pl.col(\"{field}\").is_not_null())\n        \
                 .then(pl.col(\"{field}\").cast(pl.UInt64).fill_null(0))\n        \
                 .otherwise(pl.lit(0, dtype=pl.UInt64))\n        \
                 .alias(\"{field}\")\n    )\n"
        )
    };

    let facts = scan(&[
        document("left.py", &query("left_plan", "input")),
        document("right.py", &query("right_plan", "output")),
    ]);

    assert!(facts.is_empty());
}

#[test]
fn renamed_pasted_ordinary_fluent_code_is_still_a_clone() {
    let query = |name: &str, builder: &str, field: &str| {
        format!(
            "def {name}({builder}):\n    return (\n        \
                 {builder}.when({builder}.column(\"{field}\").is_not_null())\n        \
                 .then({builder}.column(\"{field}\").cast(\"integer\").fill_null(0))\n        \
                 .otherwise({builder}.literal(0, dtype=\"integer\"))\n        \
                 .alias(\"{field}\")\n    )\n"
        )
    };

    let facts = scan(&[
        document("left.py", &query("left_plan", "builder", "input")),
        document("right.py", &query("right_plan", "query", "output")),
    ]);

    assert_eq!(paths(&facts), vec![vec!["left.py", "right.py"]]);
}

#[test]
fn a_lazy_table_plan_remains_declarative_through_local_aliases() {
    let query = |name: &str, table: &str, field: &str| {
        format!(
            "import polars as pl\n\ndef {name}({table}: Table):\n    facts = \
                 {table}.lazy(\"facts\")\n    selected = facts.filter(pl.col(\"{field}\") > \
                 0)\n    retained = selected\n    grouped = \
                 retained.group_by(\"owner\")\n    counts = \
                 grouped.agg(pl.len().alias(\"count\"))\n    filled = \
                 counts.with_columns(pl.col(\"count\").fill_null(0))\n    ordered = \
                 filled.sort(\"owner\")\n    limited = ordered.head(10)\n    renamed = \
                 limited.rename({{\"count\": \"total\"}})\n    unique = \
                 renamed.unique(\"owner\")\n    return unique.select(\"owner\", \"total\")\n"
        )
    };

    let facts = scan(&[
        document("left.py", &query("left_plan", "subject", "input")),
        document("right.py", &query("right_plan", "table", "output")),
    ]);

    assert!(facts.is_empty());
}

#[test]
fn declarative_plans_are_boundaries_between_ordinary_tokens() {
    let query = |name: &str, field: &str| {
        format!(
            "import polars as pl\n\ndef {name}(subject: Table):\n    facts = \
             subject.lazy(\"facts\")\n    selected = facts.filter(pl.col(\"{field}\") > 0)\n    \
             findings = selected.select(\"fact_id\", \"ordinal\")\n    return \
             RuleQuery.integer(facts, pl.col(\"value\"), findings=findings)\n"
        )
    };

    let facts = scan(&[
        document("left.py", &query("left_plan", "input")),
        document("right.py", &query("right_plan", "output")),
    ]);

    assert!(facts.is_empty());
}

#[test]
fn the_same_fluent_shape_without_table_provenance_remains_a_clone() {
    let query = |name: &str, service: &str, field: &str| {
        format!(
            "def {name}({service}, criteria):\n    facts = \
                 {service}.load(\"facts\")\n    selected = \
                 facts.filter(criteria.column(\"{field}\") > 0)\n    retained = selected\n    \
                 grouped = retained.group_by(\"owner\")\n    counts = \
                 grouped.aggregate(criteria.count().alias(\"count\"))\n    filled = \
                 counts.with_columns(criteria.column(\"count\").fill_missing(0))\n    ordered = \
                 filled.sort(\"owner\")\n    limited = ordered.head(10)\n    renamed = \
                 limited.rename({{\"count\": \"total\"}})\n    unique = \
                 renamed.unique(\"owner\")\n    return unique.select(\"owner\", \"total\")\n"
        )
    };

    let facts = scan(&[
        document("left.py", &query("left_plan", "service", "input")),
        document("right.py", &query("right_plan", "gateway", "output")),
    ]);

    assert_eq!(paths(&facts), vec![vec!["left.py", "right.py"]]);
}

#[test]
fn two_bodies_that_do_different_work_are_never_one_clone() {
    let other = "def report(rows):\n    for row in rows:\n        print(row.name, row.value, \
                     row.owner, row.state, row.updated, row.created, row.id, row.kind)\n";

    let facts = scan(&[
        document("left.py", &body("total_over", "total", "row")),
        document("right.py", other),
    ]);

    assert!(facts.is_empty());
}

#[test]
fn matching_grammar_with_different_data_flow_is_not_a_clone() {
    let left = "def left(source):\n    first = source.read()\n    second = source.read()\n    \
                one = normalize(first)\n    two = normalize(second)\n    three = combine(one, two)\n    \
                four = validate(three, first)\n    five = validate(four, second)\n    return \
                finish(five, one, two)\n";
    let right = "def right(source):\n    alpha = source.read()\n    beta = source.read()\n    \
                 gamma = normalize(alpha)\n    delta = normalize(alpha)\n    epsilon = combine(gamma, \
                 delta)\n    zeta = validate(epsilon, beta)\n    eta = validate(zeta, beta)\n    \
                 return finish(eta, gamma, delta)\n";

    assert!(scan(&[document("left.py", left), document("right.py", right)]).is_empty());
}

#[test]
fn a_repeat_shorter_than_the_window_is_left_alone() {
    let short = "def add(left, right):\n    return left + right\n";

    assert!(scan(&[document("a.py", short), document("b.py", short)]).is_empty());
}

#[test]
fn one_copied_run_is_reported_once_rather_than_once_per_window() {
    let source = body("total_over", "total", "row");
    let facts = scan(&[document("left.py", &source), document("right.py", &source)]);

    assert_eq!(facts.len(), 1);
    let length = facts[0]["token_length"].as_u64().expect("token length");
    assert!(
        length > WINDOW as u64,
        "{length} should have grown past {WINDOW}"
    );
}

#[test]
fn a_third_copy_joins_the_group_it_belongs_to() {
    let source = body("total_over", "total", "row");
    let facts = scan(&[
        document("a.py", &source),
        document("b.py", &source),
        document("c.py", &source),
    ]);

    assert_eq!(paths(&facts), vec![vec!["a.py", "b.py", "c.py"]]);
    assert_eq!(facts[0]["repository_line_count"], 30);
}

#[test]
fn a_typescript_copy_is_found_by_the_brace_reader() {
    let facts = scan(&[
        document("left.ts", &brace_body("totalOver", "total", "row")),
        document("right.ts", &brace_body("sumAbove", "carried", "item")),
    ]);

    assert_eq!(paths(&facts), vec![vec!["left.ts", "right.ts"]]);
    assert_eq!(facts[0]["language"], "typescript");
}

#[test]
fn a_rust_copy_is_found_through_its_own_token_stream() {
    let facts = scan(&[
        document("left.rs", &rust_body("total_over", "total", "row")),
        document("right.rs", &rust_body("sum_above", "carried", "item")),
    ]);

    assert_eq!(paths(&facts), vec![vec!["left.rs", "right.rs"]]);
    assert_eq!(facts[0]["language"], "rust");
}

#[test]
fn polars_table_macros_do_not_turn_column_schemas_into_behavior_clones() {
    let table = |name: &str, prefix: &str| {
        let columns = (0..24)
                .map(|index| {
                    format!(
                        "        \"{prefix}_{index}\" => rows.iter().map(|row| row.field_{index}.as_str()).collect::<Vec<_>>(),\n"
                    )
                })
                .collect::<String>();
        format!("fn {name}(rows: &[Row]) -> DataFrame {{\n    df![\n{columns}    ]\n}}\n")
    };

    let facts = scan(&[
        document("left.rs", &table("left", "input")),
        document("right.rs", &table("right", "output")),
    ]);

    assert!(facts.is_empty());
}

#[test]
fn executable_macro_bodies_still_contribute_clone_tokens() {
    let wrapped = |name: &str, total: &str, item: &str| {
        let body = rust_body(name, total, item);
        body.replacen('{', "{\n    execute! {", 1)
            .replacen("\n}\n", "\n    }\n}\n", 1)
    };

    let facts = scan(&[
        document("left.rs", &wrapped("total_over", "total", "row")),
        document("right.rs", &wrapped("sum_above", "carried", "item")),
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
        document("left.rs", &commented("one explanation")),
        document("right.rs", &commented("another explanation entirely")),
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
