use super::*;

mod continuation;

fn document<R: AsRef<str>, S: AsRef<str>>(relative: R, source: S) -> Document {
    Document {
        relative: relative.as_ref().to_string(),
        source: source.as_ref().to_string(),
    }
}

/// One body long enough to clear the window, written with whatever names it is given.
fn body<N: AsRef<str>, T: AsRef<str>, I: AsRef<str>>(name: N, total: T, item: I) -> String {
    let (name, total, item) = (name.as_ref(), total.as_ref(), item.as_ref());
    format!(
        "def {name}(rows, limit):\n    {total} = 0\n    for {item} in rows:\n        if \
             {item} > limit:\n            {total} = {total} + {item} * 2\n        else:\n          \
             {total} = {total} - 1\n    if {total} < 0:\n        return 0\n    return {total}\n"
    )
}

/// The same body again, written the way a brace language writes it.
fn brace_body<N: AsRef<str>, T: AsRef<str>, I: AsRef<str>>(name: N, total: T, item: I) -> String {
    let (name, total, item) = (name.as_ref(), total.as_ref(), item.as_ref());
    format!(
        "export function {name}(rows: Row[], limit: number): number {{\n  let {total} = 0;\n  \
             for (const {item} of rows) {{\n    if ({item}.value > limit) {{\n      {total} = \
             {total} + {item}.value * 2;\n    }} else {{\n      {total} = {total} - 1;\n    }}\n  \
             }}\n  if ({total} < 0) {{\n    return 0;\n  }}\n  return {total};\n}}\n"
    )
}

/// The same body once more, written the way Rust writes it.
fn rust_body<N: AsRef<str>, T: AsRef<str>, I: AsRef<str>>(name: N, total: T, item: I) -> String {
    let (name, total, item) = (name.as_ref(), total.as_ref(), item.as_ref());
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
        document("left.py", body("total_over", "total", "row")),
        document("right.py", body("sum_above", "carried", "item")),
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
        document("left.py", query("left_plan", "input")),
        document("right.py", query("right_plan", "output")),
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
        document("left.py", query("left_plan", "builder", "input")),
        document("right.py", query("right_plan", "query", "output")),
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
        document("left.py", query("left_plan", "subject", "input")),
        document("right.py", query("right_plan", "table", "output")),
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
        document("left.py", query("left_plan", "input")),
        document("right.py", query("right_plan", "output")),
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
        document("left.py", query("left_plan", "service", "input")),
        document("right.py", query("right_plan", "gateway", "output")),
    ]);

    assert_eq!(paths(&facts), vec![vec!["left.py", "right.py"]]);
}

#[test]
fn two_bodies_that_do_different_work_are_never_one_clone() {
    let other = "def report(rows):\n    for row in rows:\n        print(row.name, row.value, \
                     row.owner, row.state, row.updated, row.created, row.id, row.kind)\n";

    let facts = scan(&[
        document("left.py", body("total_over", "total", "row")),
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
        document("left.ts", brace_body("totalOver", "total", "row")),
        document("right.ts", brace_body("sumAbove", "carried", "item")),
    ]);

    assert_eq!(paths(&facts), vec![vec!["left.ts", "right.ts"]]);
    assert_eq!(facts[0]["language"], "typescript");
}

#[test]
fn a_rust_copy_is_found_through_its_own_token_stream() {
    let facts = scan(&[
        document("left.rs", rust_body("total_over", "total", "row")),
        document("right.rs", rust_body("sum_above", "carried", "item")),
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
        document("left.rs", table("left", "input")),
        document("right.rs", table("right", "output")),
    ]);

    assert!(facts.is_empty());
}
