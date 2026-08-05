use super::*;
use ruff_python_parser::parse_module;

fn declarations_of(text: &str) -> Vec<Value> {
    let document = crate::discovery::Document {
        relative: "src/example.py".to_string(),
        source: text.to_string(),
    };
    let source = Source::new(&document);
    let parsed = parse_module(text).expect("the fixture parses");
    declarations(&source, parsed.syntax())
}

#[test]
fn a_declaration_carries_its_own_source_and_its_own_tree() {
    let facts = declarations_of(
        "def rename(name: str) -> str:\n    bare = name.lstrip('_')\n    return f'is_{bare}'\n",
    );

    assert_eq!(
        (facts.len(), &facts[0]["qualname"], &facts[0]["kind"]),
        (1, &Value::from("rename"), &Value::from("callable"))
    );
    assert!(
        facts[0]["source"]
            .as_str()
            .unwrap_or_default()
            .starts_with("def rename")
    );
    let tree = unpack(&facts[0]);
    let body = tree["children"].as_array().unwrap();
    let kinds: Vec<&str> = body
        .iter()
        .map(|item| item["kind"].as_str().unwrap_or_default())
        .collect();
    assert_eq!(kinds, vec!["name", "name", "binding", "return"]);
    assert_eq!(body[2]["name"], "bare");
    assert!(tree.get("text").is_none());
    assert!(body.iter().all(|node| node.get("text").is_none()));
}

#[test]
fn a_class_tree_stops_at_the_methods_that_carry_their_own_facts() {
    let facts = declarations_of(
        "class Engine:\n    def run(self):\n        total = 0\n        return total\n",
    );
    let held = unpack(&facts[0]);
    let method = unpack(&facts[1]);

    assert_eq!(facts[0]["qualname"], "Engine");
    assert_eq!(held["children"][0]["kind"], "callable");
    assert!(
        held["children"][0]["children"]
            .as_array()
            .unwrap()
            .is_empty(),
        "a method body inside a class tree would count every defect in it twice"
    );
    let body: Vec<&str> = method["children"]
        .as_array()
        .unwrap()
        .iter()
        .map(|item| item["name"].as_str().unwrap_or_default())
        .collect();
    assert!(
        body.contains(&"total"),
        "the method keeps its own body, {body:?}"
    );
}

#[test]
fn a_nested_declaration_is_named_by_what_holds_it() {
    let facts = declarations_of("class Engine:\n    def run(self) -> int:\n        return 1\n");

    assert_eq!(
        facts
            .iter()
            .map(|fact| fact["qualname"].as_str().unwrap_or_default())
            .collect::<Vec<_>>(),
        vec!["Engine", "Engine.run"]
    );
}

#[test]
fn the_tree_reaches_the_names_and_the_calls_a_body_states() {
    let facts = declarations_of("def run(values):\n    return sorted(values.keys())\n");
    let mut kinds = Vec::new();
    let tree = unpack(&facts[0]);
    let mut pending = vec![&tree];
    while let Some(node) = pending.pop() {
        kinds.push((
            node["kind"].as_str().unwrap_or_default().to_string(),
            node["name"].as_str().unwrap_or_default().to_string(),
        ));
        pending.extend(node["children"].as_array().into_iter().flatten());
    }

    assert!(kinds.contains(&("call".to_string(), "sorted".to_string())));
    assert!(kinds.contains(&("member".to_string(), "keys".to_string())));
    assert!(kinds.contains(&("name".to_string(), "values".to_string())));
}

fn kinds_used(tree: &Value) -> std::collections::BTreeSet<String> {
    let mut found = std::collections::BTreeSet::new();
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
fn every_kind_a_tree_uses_is_in_the_shared_vocabulary() {
    let facts = declarations_of(
        "class Engine:\n    def run(self, values):\n        found = [v for v in values if v]\n        try:\n            return sorted(found)[0]\n        except IndexError:\n            raise ValueError('empty')\n",
    );
    let known: std::collections::BTreeSet<&str> = KINDS.iter().copied().collect();

    for fact in &facts {
        for kind in kinds_used(&unpack(fact)) {
            assert!(
                known.contains(kind.as_str()),
                "{kind} is not in the vocabulary"
            );
        }
    }
}

#[test]
fn a_deep_expression_reaches_the_tree_without_a_private_ceiling() {
    let document = crate::discovery::Document {
        relative: "src/example.py".to_string(),
        source: "def run():\n    return one(two(three(four(five(six(seven(eight())))))))\n"
            .to_string(),
    };
    let source = Source::new(&document);
    let parsed = parse_module(&source.text).expect("the fixture parses");

    let facts = declarations(&source, parsed.syntax());
    let mut names = Vec::new();
    let tree = unpack(&facts[0]);
    let mut pending = vec![&tree];
    while let Some(node) = pending.pop() {
        names.push(node["name"].as_str().unwrap_or_default());
        pending.extend(node["children"].as_array().into_iter().flatten());
    }

    assert!(names.contains(&"eight"));
}
