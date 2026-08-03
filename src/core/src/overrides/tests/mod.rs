use super::*;
use crate::discovery::Document;

fn facts_of(source: &str) -> Vec<Value> {
    let graph = crate::graph::build(
        "repo",
        &[
            Document {
                relative: "pkg/__init__.py".to_string(),
                source: String::new(),
            },
            Document {
                relative: "pkg/example.py".to_string(),
                source: source.to_string(),
            },
        ],
    )
    .expect("the graph builds");
    pairs(&graph)
}

fn link<'a>(facts: &'a [Value], derived: &str, base: &str) -> &'a Value {
    facts
        .iter()
        .find(|fact| {
            fact["derived"]
                .as_str()
                .is_some_and(|name| name.ends_with(derived))
                && fact["base"]
                    .as_str()
                    .is_some_and(|name| name.ends_with(base))
        })
        .expect("the link is missing")
}

fn names(fact: &Value, side: &str) -> Vec<String> {
    fact[side]
        .as_array()
        .expect("a declaration list")
        .iter()
        .map(|item| item["name"].as_str().unwrap_or_default().to_string())
        .collect()
}

#[test]
fn a_link_carries_both_declarations_of_the_member_that_crosses_it() {
    let facts = facts_of(
        "class Base:\n    def run(self, count):\n        return count\n\n\nclass Engine(Base):\n    def run(self, total):\n        return total\n",
    );
    let found = link(&facts, "Engine", "Base");

    assert_eq!(facts.len(), 1);
    assert_eq!(found["depth"], 1);
    assert_eq!(found["overridden_member_count"], 1);
    assert_eq!(names(found, "inherited"), ["run"]);
    assert_eq!(found["inherited"][0]["parameters"][1]["name"], "count");
    assert_eq!(found["declared"][0]["parameters"][1]["name"], "total");
    assert!(
        found["declared"][0]["source"]
            .as_str()
            .is_some_and(|source| source.starts_with("def run"))
    );
    assert_eq!(found["base_names"][0], "Base");
}

#[test]
fn a_parameter_states_how_it_binds_and_whether_a_caller_may_leave_it_out() {
    let facts = facts_of(
        "class Base:\n    def run(self, first, /, second, *rest, flag=True, **extra):\n        return first\n\n\nclass Engine(Base):\n    def run(self, first, /, second, *rest, flag=True, **extra):\n        return second\n",
    );
    let stated = &link(&facts, "Engine", "Base")["inherited"][0]["parameters"];
    let kinds: Vec<&str> = stated
        .as_array()
        .expect("a parameter list")
        .iter()
        .filter_map(|item| item["kind"].as_str())
        .collect();

    assert_eq!(
        kinds,
        [
            "positional_only",
            "positional_only",
            "positional_or_keyword",
            "var_positional",
            "keyword_only",
            "var_keyword",
        ]
    );
    assert_eq!(stated[4]["name"], "flag");
    assert_eq!(stated[4]["has_default"], true);
    assert_eq!(stated[2]["has_default"], false);
}

#[test]
fn the_nearest_ancestor_owns_a_member_every_class_above_declares() {
    let facts = facts_of(
        "class Root:\n    def run(self):\n        return 1\n\n\nclass Middle(Root):\n    def run(self):\n        return 2\n\n\nclass Leaf(Middle):\n    def run(self):\n        return 3\n",
    );

    assert_eq!(names(link(&facts, "Leaf", "Middle"), "inherited"), ["run"]);
    assert!(names(link(&facts, "Leaf", "Root"), "inherited").is_empty());
    assert_eq!(link(&facts, "Leaf", "Root")["depth"], 2);
}

#[test]
fn a_decorator_and_an_await_travel_with_the_half_that_wrote_them() {
    let facts = facts_of(
        "from typing import final\n\n\nclass Base:\n    @property\n    def size(self):\n        return 1\n\n    @final\n    async def fetch(self):\n        return 2\n\n\nclass Engine(Base):\n    def size(self):\n        return 3\n\n    def fetch(self):\n        return 4\n",
    );
    let found = link(&facts, "Engine", "Base");

    assert_eq!(found["inherited"][0]["name"], "fetch");
    assert_eq!(found["inherited"][0]["decorators"][0], "final");
    assert_eq!(found["inherited"][0]["asynchronous"], true);
    assert_eq!(found["inherited"][1]["decorators"][0], "property");
    assert_eq!(found["declared"][0]["asynchronous"], false);
}

#[test]
fn an_attribute_and_a_method_are_told_apart_by_the_parameters_only_one_has() {
    let facts = facts_of(
        "class Base:\n    def __init__(self):\n        self.run = None\n\n\nclass Engine(Base):\n    def run(self):\n        return 1\n",
    );
    let found = link(&facts, "Engine", "Base");
    let hidden = found["inherited"]
        .as_array()
        .expect("declarations")
        .iter()
        .find(|item| item["name"] == "run")
        .expect("the attribute");

    assert!(hidden["parameters"].is_null());
    assert_eq!(found["declared"][0]["parameters"][0]["name"], "self");
}

#[test]
fn an_initializer_states_whose_initializer_it_called() {
    let facts = facts_of(
        "class Base:\n    def __init__(self):\n        self.total = 0\n\n\nclass Other:\n    def __init__(self):\n        self.count = 0\n\n\nclass Polite(Base):\n    def __init__(self):\n        super().__init__()\n\n\nclass Rude(Base):\n    def __init__(self):\n        Other.__init__(self)\n\n\nclass Silent(Base):\n    def __init__(self):\n        self.total = 1\n",
    );

    assert_eq!(
        link(&facts, "Polite", "Base")["initializer_calls"][0],
        "super"
    );
    assert_eq!(
        link(&facts, "Rude", "Base")["initializer_calls"][0],
        "Other"
    );
    assert!(
        link(&facts, "Silent", "Base")["initializer_calls"]
            .as_array()
            .expect("a call list")
            .is_empty()
    );
}

#[test]
fn an_unresolved_base_is_named_without_pretending_to_be_a_link() {
    let facts = facts_of(
        "from abc import ABC, abstractmethod\n\n\nclass Base(ABC):\n    @abstractmethod\n    def run(self):\n        return 1\n\n\nclass Engine(Base):\n    def other(self):\n        return 2\n",
    );
    let found = link(&facts, "Engine", "Base");
    let ancestors: Vec<&str> = found["ancestor_names"]
        .as_array()
        .expect("names")
        .iter()
        .filter_map(Value::as_str)
        .collect();

    assert_eq!(facts.len(), 1);
    assert_eq!(found["base_names"][0], "Base");
    assert!(ancestors.contains(&"ABC"));
    assert_eq!(found["inherited"][0]["decorators"][0], "abstractmethod");
}

#[test]
fn a_class_nothing_in_this_repository_is_above_produces_no_link() {
    assert!(facts_of("class Alone:\n    def run(self):\n        return 1\n").is_empty());
}

#[test]
fn a_link_without_an_override_states_that_no_member_is_overridden() {
    let facts = facts_of(
        "class Base:\n    def run(self):\n        return 1\n\n\nclass Engine(Base):\n    def stop(self):\n        return 2\n",
    );

    assert_eq!(link(&facts, "Engine", "Base")["overridden_member_count"], 0);
}
