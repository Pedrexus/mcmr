use super::*;

fn collections_in(body: &str) -> Vec<Value> {
    facts_for(body, FactFamily("CollectionFact"))[0]["local_collections"]
        .as_array()
        .cloned()
        .unwrap_or_default()
}

#[test]
fn a_literal_read_only_by_a_loop_states_that_every_read_iterates() {
    let found = collections_in(
        "def run():\n    formats = (\"json\", \"toml\")\n    for name in formats:\n        print(name)\n",
    );

    assert_eq!(found.len(), 1);
    assert_eq!(found[0]["name"], "formats");
    assert_eq!(found[0]["kind"], "tuple");
    assert_eq!(found[0]["all_reads_are_iteration"], true);
    assert_eq!(found[0]["all_reads_are_membership"], false);
    assert_eq!(found[0]["has_homogeneous_literals"], true);
}

#[test]
fn a_comprehension_iterates_the_same_way_a_loop_statement_does() {
    let found = collections_in(
        "def run():\n    formats = [\"json\", \"toml\"]\n    return [name.upper() for name in formats]\n",
    );

    assert_eq!(found[0]["all_reads_are_iteration"], true);
}

#[test]
fn a_literal_read_only_by_a_membership_test_states_that_and_its_uniqueness() {
    let found = collections_in(
        "def run(value):\n    formats = [\"json\", \"toml\", \"json\"]\n    return value in formats\n",
    );

    assert_eq!(found[0]["all_reads_are_membership"], true);
    assert_eq!(found[0]["all_reads_are_iteration"], false);
    assert_eq!(found[0]["values_are_unique"], false);
}

#[test]
fn one_representation_sensitive_read_leaves_both_claims_false() {
    let found = collections_in(
        "def run():\n    formats = [\"json\", \"toml\"]\n    for name in formats:\n        print(name)\n    return formats[0]\n",
    );

    assert_eq!(found[0]["all_reads_are_iteration"], false);
    assert_eq!(found[0]["all_reads_are_membership"], false);
}

#[test]
fn a_module_constant_and_a_rebound_local_are_not_candidates() {
    assert!(collections_in("FORMATS = [\"json\", \"toml\"]\n").is_empty());
    assert!(
        collections_in(
            "def run(flag):\n    formats = [\"json\", \"toml\"]\n    if flag:\n        formats = [\"yaml\"]\n    return formats\n",
        )
        .is_empty()
    );
}

#[test]
fn a_mixed_literal_is_not_homogeneous_and_a_call_is_not_a_literal() {
    let found = collections_in(
        "def run():\n    mixed = [\"json\", 2]\n    built = [load()]\n    return mixed, built\n",
    );

    assert_eq!(found[0]["has_homogeneous_literals"], false);
    assert_eq!(found[1]["has_homogeneous_literals"], false);
}

#[test]
fn fixed_string_repetition_is_distinct_from_an_already_repeated_literal() {
    let facts = facts_for(
        concat!(
            "plain = \"====\"\n",
            "left = \"=-\" * 4\n",
            "right = 3 * \"~\"\n",
            "dynamic = \"-\" * width\n",
        ),
        FactFamily("StringExpressionFact"),
    );
    let expressions = facts[0]["expressions"]
        .as_array()
        .expect("string expressions are a list");

    assert_eq!(
        json!([
            expressions[0]["kind"],
            expressions[1]["kind"],
            expressions[1]["literal"],
            expressions[1]["repetition_count"],
            expressions[2]["kind"],
            expressions[2]["literal"],
            expressions[2]["repetition_count"],
            expressions[3]["kind"],
        ]),
        json!([
            "literal",
            "fixed-repetition",
            "=-",
            4,
            "fixed-repetition",
            "~",
            3,
            "literal"
        ])
    );
    assert!(expressions[0].get("repetition_count").is_none());
}

#[test]
fn string_expression_facts_exclude_docstrings() {
    let facts = facts_for(
        concat!(
            "\"\"\"Module documentation.\"\"\"\n",
            "def render():\n",
            "    \"\"\"Callable documentation.\"\"\"\n",
            "    return \"rendered value\"\n",
        ),
        FactFamily("StringExpressionFact"),
    );
    let expressions = facts[0]["expressions"]
        .as_array()
        .expect("string expressions are a list");

    assert_eq!(expressions.len(), 1);
    assert_eq!(expressions[0]["runtime_value"], "rendered value");
}

#[test]
fn enum_metadata_candidates_keep_maps_with_unresolved_keys() {
    let facts = facts_for(
        concat!(
            "from enum import StrEnum, auto\n\n",
            "class Stage(StrEnum):\n",
            "    PLACED = auto()\n\n",
            "LABELS = {Stage.PLACED: 'Placed', 'other': 'Other'}\n",
        ),
        FactFamily("LiteralGroupFact"),
    );
    let maps = facts[0]["enum_metadata_maps"].as_array().unwrap();

    assert_eq!(maps.len(), 1);
    assert_eq!(maps[0]["enum_name"], "Stage");
    assert_eq!(maps[0]["all_keys_resolve_to_enum"], false);
}

#[test]
fn every_arm_of_a_chain_states_how_much_it_does_and_whether_it_answers() {
    let facts = facts_for(
        "def run(kind, log):\n    if kind == \"pbs\":\n        return 1\n    elif kind == \"slurm\":\n        log(kind)\n        return 2\n    elif kind == \"ssh\":\n        log(kind)\n    else:\n        return 0\n",
        FactFamily("BranchFact"),
    );
    let arms = facts[0]["chains"][0]["arms"].as_array().unwrap();

    assert_eq!(facts[0]["chains"][0]["has_fallback"], true);
    assert_eq!(
        arms.iter()
            .map(|arm| arm["statement_count"].as_u64().unwrap_or_default())
            .collect::<Vec<_>>(),
        [1, 2, 1]
    );
    assert_eq!(
        arms.iter()
            .map(|arm| arm["returns_value"].as_bool().unwrap_or_default())
            .collect::<Vec<_>>(),
        [true, true, false]
    );
}
