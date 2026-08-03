use super::*;
use crate::source::Source;
use ruff_python_ast::ModModule;
use ruff_python_parser::parse_module;
use serde_json::{Value, json};

fn fact(document: crate::discovery::Document, extract: fn(&Source, &ModModule) -> Value) -> Value {
    let parsed = parse_module(&document.source).expect("the fixture parses");
    extract(&Source::new(&document), parsed.syntax())
}

#[test]
fn test_function_ownership_stops_at_nested_declarations_and_keeps_its_span() {
    let extracted = fact(
        crate::discovery::Document {
            relative: "tests/test_owned.py".to_string(),
            source: concat!(
                "def test_outer():\n",
                "    \"\"\"Exercise the outer behavior.\"\"\"\n",
                "    value = 1\n",
                "    if value:\n",
                "        assert value\n",
                "    def helper():\n",
                "        if value:\n",
                "            danger()\n",
                "    helper()\n",
                "    return value\n",
            )
            .to_string(),
        },
        test_functions,
    );
    let test = &extracted["tests"][0];

    assert_eq!(test["owned_statement_count"], 6);
    assert_eq!(test["owned_conditional_count"], 1);
    assert_eq!(test["calls"].as_array().expect("test calls").len(), 1);
    assert_eq!(test["node"]["span"]["path"], "tests/test_owned.py");
    assert_eq!(test["node"]["span"]["start_line"], 1);
    assert_eq!(test["node"]["span"]["end_line"], 10);
}

#[test]
fn annotation_recipe_keeps_only_reusable_annotated_constraints() {
    let text = concat!(
        "from typing import Annotated\n",
        "from pydantic import Field, StringConstraints\n",
        "plain: str\n",
        "sequence: list[str]\n",
        "name: Annotated[str, StringConstraints(min_length=1)]\n",
        "count: Annotated[int, Field(ge=0)] | None\n",
    );
    let extracted = fact(
        crate::discovery::Document {
            relative: "models.py".to_string(),
            source: text.to_string(),
        },
        annotations,
    );
    let recipes: Vec<&str> = extracted["annotations"]
        .as_array()
        .expect("annotations")
        .iter()
        .map(|annotation| {
            annotation["constraint_recipe"]
                .as_str()
                .expect("constraint recipe")
        })
        .collect();

    assert_eq!(
        recipes,
        [
            "",
            "",
            "Annotated[str, StringConstraints(min_length=1)]",
            "Annotated[int, Field(ge=0)]",
        ]
    );
}

#[test]
fn prose_keeps_each_docstring_as_its_own_section_and_reads_every_sentence() {
    let fact = fact(
        crate::discovery::Document {
            relative: "prose.py".to_string(),
            source: concat!(
                "def first():\n",
                "    \"\"\"Open the file. Return its content now!\"\"\"\n",
                "\n",
                "class Reader:\n",
                "    \"\"\"Read values safely? Keep failures visible.\"\"\"\n",
            )
            .to_string(),
        },
        prose,
    );
    let sections = fact["sections"].as_array().expect("prose sections");

    assert_eq!(sections.len(), 2);
    assert_eq!(
        sections[0]["text"],
        "Open the file. Return its content now!"
    );
    assert_eq!(sections[0]["node"]["span"]["path"], "prose.py");
    assert_eq!(sections[0]["sentence_word_counts"], json!([3, 4]));
    assert_eq!(sections[0]["sentence_openers"], json!(["open", "return"]));
    assert_eq!(sections[1]["sentence_word_counts"], json!([3, 3]));
    assert_eq!(sections[1]["sentence_openers"], json!(["read", "keep"]));
}

#[test]
fn query_facts_are_resolved_once_with_their_real_chain_evidence() {
    let text = concat!(
        "from sqlmodel import Field as Column, SQLModel, Session as DbSession, select as choose\n\n",
        "class Hero(SQLModel, table=True):\n",
        "    id: int | None = Column(default=None, primary_key=True)\n\n",
        "def load(session: DbSession, hero_id: int):\n",
        "    for _ in range(2):\n",
        "        session.commit()\n",
        "    rows = session.execute(choose(Hero)).scalars()\n",
        "    direct = session.exec(choose(Hero)).scalars()\n",
        "    hero = session.exec(choose(Hero).where(Hero.id == hero_id)).first()\n",
        "    fresh = session.exec(choose(Hero).where(Hero.id == hero_id).execution_options(populate_existing=True)).first()\n",
    );
    let fact = fact(
        crate::discovery::Document {
            relative: "shop/database.py".to_string(),
            source: text.to_string(),
        },
        queries,
    );
    let operations = fact["operations"].as_array().expect("query operations");
    let kinds: Vec<&str> = operations
        .iter()
        .map(|operation| operation["kind"].as_str().expect("operation kind"))
        .collect();

    assert_eq!(
        kinds,
        [
            "session_commit",
            "execute_scalars",
            "exec_scalars",
            "primary_key_first",
            "primary_key_first",
        ]
    );
    assert_eq!(
        json!([
            operations[0]["is_inside_loop"],
            operations[1]["execute_segment"]["text"],
            operations[1]["scalars_segment"]["text"],
            operations[3]["has_primary_key_equality"],
            operations[3]["has_execution_options"],
            operations[4]["has_execution_options"],
        ]),
        json!([true, "execute", ".scalars()", true, false, true])
    );
}

#[test]
fn unresolved_database_like_calls_are_not_claimed_as_sqlmodel() {
    let text = "def load(session, statement):\n    return session.exec(statement).scalars()\n";
    assert_eq!(
        fact(
            crate::discovery::Document {
                relative: "shop/database.py".to_string(),
                source: text.to_string(),
            },
            queries,
        )["operations"],
        json!([])
    );
}

#[test]
fn set_loop_candidate_retains_a_single_filter_and_exact_source_nodes() {
    let text = concat!(
        "def collect(source):\n",
        "    values = set()\n",
        "    for item in source:\n",
        "        if item.valid:\n",
        "            values.add(item.key)\n",
        "    return values\n",
    );
    let fact = fact(
        crate::discovery::Document {
            relative: "collections.py".to_string(),
            source: text.to_string(),
        },
        comprehensions,
    );
    let candidates = fact["set_loop_candidates"]
        .as_array()
        .expect("set loop candidates");

    assert_eq!(candidates.len(), 1);
    assert_eq!(candidates[0]["name"], "values");
    assert_eq!(candidates[0]["conditional_count"], 1);
    assert_eq!(candidates[0]["element"]["text"], "item.key");
    assert_eq!(candidates[0]["target"]["text"], "item");
    assert_eq!(candidates[0]["iterable"]["text"], "source");
    assert_eq!(candidates[0]["conditions"][0]["text"], "item.valid");
}

#[test]
fn set_loop_candidates_honor_scope_and_semantic_suppressions() {
    let text = concat!(
        "module_values = set()\n",
        "for module_item in source:\n",
        "    module_values.add(module_item)\n\n",
        "class Holder:\n",
        "    class_values = set()\n",
        "    for class_item in source:\n",
        "        class_values.add(class_item)\n\n",
        "def shadowed(set, source):\n",
        "    values = set()\n",
        "    for item in source:\n",
        "        values.add(item)\n\n",
        "def handled(source):\n",
        "    try:\n",
        "        consume(source)\n",
        "    except Error:\n",
        "        values = set()\n",
        "        for item in source:\n",
        "            values.add(item)\n\n",
        "def reused(source):\n",
        "    values = set()\n",
        "    for item in source:\n",
        "        values.add(item)\n",
        "    return item\n\n",
        "def self_read(source):\n",
        "    values = set()\n",
        "    for item in source:\n",
        "        values.add((item, len(values)))\n\n",
        "def introspected(source):\n",
        "    values = set()\n",
        "    for item in source:\n",
        "        values.add(item)\n",
        "    snapshot = locals()\n",
        "\nasync def asynchronous(source):\n",
        "    values = set()\n",
        "    async for item in source:\n",
        "        values.add(item)\n",
        "\ndef loop_else(source):\n",
        "    values = set()\n",
        "    for item in source:\n",
        "        values.add(item)\n",
        "    else:\n",
        "        completed()\n",
        "\ndef multiple_effects(source):\n",
        "    values = set()\n",
        "    for item in source:\n",
        "        values.add(item)\n",
        "        log(item)\n",
        "\ndef assignment_expression(source):\n",
        "    values = set()\n",
        "    for item in source:\n",
        "        values.add(saved := item)\n",
        "\nasync def awaited(source):\n",
        "    values = set()\n",
        "    for item in source:\n",
        "        values.add(await normalize(item))\n",
        "\ndef yielded(source):\n",
        "    values = set()\n",
        "    for item in source:\n",
        "        values.add((yield item))\n",
        "\ndef attribute_target(source, holder):\n",
        "    values = set()\n",
        "    for holder.item in source:\n",
        "        values.add(holder.item)\n",
        "\ndef prefilled(source):\n",
        "    values = set(source)\n",
        "    for item in source:\n",
        "        values.add(item)\n",
        "\ndef conditional_else(source):\n",
        "    values = set()\n",
        "    for item in source:\n",
        "        if item.ready:\n",
        "            values.add(item)\n",
        "        else:\n",
        "            reject(item)\n",
        "\ndef closure_shadow(source):\n",
        "    set = custom_set\n",
        "    def nested():\n",
        "        values = set()\n",
        "        for item in source:\n",
        "            values.add(item)\n",
    );
    assert_eq!(
        fact(
            crate::discovery::Document {
                relative: "collections.py".to_string(),
                source: text.to_string(),
            },
            comprehensions,
        )["set_loop_candidates"],
        json!([])
    );
}

#[test]
fn set_loop_comments_keep_the_finding_but_suppress_the_edit_node() {
    let text = concat!(
        "def collect(source):\n",
        "    values = set()\n",
        "    for item in source:\n",
        "        values.add(item)  # preserve this explanation\n",
    );
    let fact = fact(
        crate::discovery::Document {
            relative: "collections.py".to_string(),
            source: text.to_string(),
        },
        comprehensions,
    );
    let candidates = fact["set_loop_candidates"]
        .as_array()
        .expect("set loop candidates");

    assert_eq!(candidates.len(), 1);
    assert_eq!(candidates[0]["element"], Value::Null);
    assert_eq!(candidates[0]["initialization"]["text"], "values = set()");
}

#[test]
fn module_binding_prevents_claiming_the_builtin_set() {
    let text = concat!(
        "set = custom_set\n\n",
        "def collect(source):\n",
        "    values = set()\n",
        "    for item in source:\n",
        "        values.add(item)\n",
    );
    assert_eq!(
        fact(
            crate::discovery::Document {
                relative: "collections.py".to_string(),
                source: text.to_string(),
            },
            comprehensions,
        )["set_loop_candidates"],
        json!([])
    );
}

mod continuation;
