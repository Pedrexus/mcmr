use super::*;
use serde_json::json;
use std::collections::BTreeSet;

#[derive(Clone, Copy)]
struct FactFamily<'a>(&'a str);

fn facts_for(source: &str, family: FactFamily<'_>) -> Vec<Value> {
    let document = Document {
        relative: "src/example.ts".to_string(),
        source: source.to_string(),
    };
    let mut facts = BTreeMap::from([(family.0.to_string(), Vec::new())]);
    extract(&document, &mut facts, &mut Stats::default());
    facts.remove(family.0).unwrap_or_default()
}

fn syntax_nodes(tree: &Value) -> Vec<(String, String)> {
    let mut pending = vec![tree];
    let mut nodes = Vec::new();
    while let Some(node) = pending.pop() {
        nodes.push((
            node["kind"].as_str().unwrap_or_default().to_string(),
            node["name"].as_str().unwrap_or_default().to_string(),
        ));
        pending.extend(node["children"].as_array().into_iter().flatten());
    }
    nodes
}

#[test]
fn an_export_is_what_public_means_in_this_language() {
    let facts = facts_for(
        "export function build(name: string) {\n  return name;\n}\n\nfunction helper() {\n  return 1;\n}\n",
        FactFamily("FunctionFact"),
    );

    assert_eq!(facts.len(), 2);
    assert_eq!(facts[0]["name"], "build");
    assert_eq!(facts[0]["visibility"], "public");
    assert_eq!(facts[1]["visibility"], "internal");
}

#[test]
fn comments_are_grouped_and_parsed_in_the_typescript_dialect() {
    let facts = facts_for(
        concat!(
            "// TODO: handle the empty case\n\n",
            "// const d = read(name);\n",
            "// const e = parse(d);\n\n",
            "// retry twice before giving up\n",
            "// @ts-expect-error\n",
            "run();\n",
        ),
        FactFamily("CommentFact"),
    );
    let groups = facts[0]["groups"].as_array().unwrap();

    assert_eq!(groups.len(), 4);
    assert_eq!(groups[0]["parses_as_source"], false);
    assert_eq!(groups[1]["line_count"], 2);
    assert_eq!(groups[1]["parses_as_source"], true);
    assert_eq!(groups[2]["parses_as_source"], false);
    assert_eq!(groups[3]["is_directive"], true);
}

#[test]
fn a_class_carries_its_members_with_the_kinds_every_language_shares() {
    let facts = facts_for(
        "export class Engine extends Base {\n  limit = 3;\n\n  constructor() {\n    super();\n  }\n\n  run() {\n    return 1;\n  }\n\n  #secret() {\n    return 2;\n  }\n}\n",
        FactFamily("ClassFact"),
    );
    let classes = facts[0]["classes"].as_array().unwrap();

    let members = classes[0]["methods"].as_array().unwrap();
    assert_eq!(
        json!([
            classes[0]["name"],
            classes[0]["visibility"],
            classes[0]["direct_bases"][0],
            classes[0]["field_count"],
            classes[0]["methods"][0]["kind"],
        ]),
        json!(["Engine", "public", "Base", 1, "constructor"])
    );
    assert!(
        classes[0]["source"]
            .as_str()
            .is_some_and(|source| source.starts_with("class Engine"))
    );
    assert!(
        classes[0]["methods"][0]["source"]
            .as_str()
            .is_some_and(|source| source.starts_with("constructor"))
    );
    assert!(
        members
            .iter()
            .any(|member| member["visibility"] == "private")
    );
}

#[test]
fn an_import_records_whether_it_stays_inside_the_project() {
    let facts = facts_for(
        "import { type User as Person } from './models';\nimport React from 'react';\nimport * as UI from './ui';\n\nconst value = Person;\n",
        FactFamily("ImportBindingFact"),
    );

    assert_eq!(facts[0]["name"], "Person");
    assert_eq!(facts[0]["imported_name"], "User");
    assert_eq!(facts[0]["is_type_only"], true);
    assert_eq!(facts[0]["is_relative"], true);
    assert_eq!(facts[0]["is_external"], false);
    assert_eq!(facts[1]["name"], "React");
    assert_eq!(facts[1]["imported_name"], "default");
    assert_eq!(facts[1]["is_external"], true);
    assert_eq!(facts[2]["imported_name"], "*");
}

#[test]
fn a_module_counts_what_it_declares() {
    let facts = facts_for(
        "export class One {}\nclass Two {}\nexport function run() {}\n",
        FactFamily("ModuleFact"),
    );

    assert_eq!(facts[0]["class_count"], 2);
    assert_eq!(facts[0]["function_count"], 1);
    assert_eq!(facts[0]["statement_count"], 3);
}

#[test]
fn function_parameters_retain_the_contract_a_caller_observes() {
    let facts = facts_for(
        concat!(
            "export function configure(\n",
            "  { path }: Options, enabled: boolean, retries = 2, quiet = true,\n",
            "  label?: string, ...names: string[]\n",
            ") {}\n",
        ),
        FactFamily("FunctionFact"),
    );
    let parameters = facts[0]["parameters"].as_array().expect("parameters");
    let names: Vec<&str> = parameters
        .iter()
        .map(|parameter| parameter["name"].as_str().expect("a parameter name"))
        .collect();
    let required: Vec<bool> = parameters
        .iter()
        .map(|parameter| {
            parameter["is_required_by_external_contract"]
                .as_bool()
                .expect("required evidence")
        })
        .collect();

    assert_eq!(
        names,
        ["{ path }", "enabled", "retries", "quiet", "label", "names"]
    );
    assert_eq!(required, [true, true, false, false, false, false]);
    assert_eq!(parameters[1]["type_name"], "boolean");
    assert_eq!(parameters[1]["has_boolean_annotation"], true);
    assert_eq!(parameters[3]["has_boolean_default"], true);
    assert!(
        parameters
            .iter()
            .all(|parameter| parameter["is_positional_only"] == true)
    );
}

#[test]
fn a_private_member_is_private_however_the_class_spelled_it() {
    let facts = facts_for(
        "export class Engine {\n  #hidden() {}\n  private closed() {}\n  protected middle() {}\n  open() {}\n}\n",
        FactFamily("FunctionFact"),
    );
    let reach: Vec<&Value> = facts.iter().map(|fact| &fact["visibility"]).collect();

    assert_eq!(reach, ["private", "private", "protected", "public"]);
}

/// The shared vocabulary, the depth arithmetic, and the chain rule, all at once.
///
/// The same program written for the reference frontend has to produce the same records, since
/// the complexity and nesting rules own one scoring model for every language. A block a
/// formatter added opens no structure and a nested callable states its own fact, so neither
/// changes what this body scores.
#[test]
fn control_increments_record_their_nesting_depth() {
    let facts = facts_for(
        concat!(
            "export function run(items: number[][]): number {\n",
            "  for (const item of items) {\n",
            "    if (item.length) {\n",
            "      return 0;\n",
            "    } else if (item.length > 2) {\n",
            "      return 1;\n",
            "    } else {\n",
            "      return 2;\n",
            "    }\n",
            "  }\n",
            "  switch (items.length) {\n",
            "    case 0:\n",
            "      break;\n",
            "    default:\n",
            "      break;\n",
            "  }\n",
            "  {\n",
            "    const held = (value: number) => (value > 0 ? 1 : 0);\n",
            "    return held(1);\n",
            "  }\n",
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
    assert_eq!(facts[0]["implementation_lines"], 19);
}

#[test]
fn syntax_facts_carry_declarations_calls_bindings_and_discarded_values() {
    let facts = facts_for(
        concat!(
            "export class Loader {\n",
            "  load(name: string): number {\n",
            "    const d = name.length;\n",
            "    if (d > 0) { console.log(d); debugger; }\n",
            "    name.length;\n",
            "    d === 3;\n",
            "    return d;\n",
            "  }\n",
            "}\n",
            "const trace = () => { console.debug(1); };\n"
        ),
        FactFamily("SyntaxFact"),
    );
    let named: Vec<&str> = facts
        .iter()
        .map(|fact| fact["qualname"].as_str().unwrap_or_default())
        .collect();

    assert_eq!(named, vec!["Loader", "Loader.load", "trace"]);
    let class = crate::syntax::unpack(&facts[0]);
    assert_eq!(
        (
            &class["children"][0]["kind"],
            class["children"][0]["children"]
                .as_array()
                .is_some_and(Vec::is_empty),
        ),
        (&json!("callable"), true)
    );
    let method = crate::syntax::unpack(&facts[1]);
    let nodes = syntax_nodes(&method);
    assert_eq!(
        (
            [
                ("binding", "d"),
                ("branch", ""),
                ("call", "console.log"),
                ("effect", "debugger"),
            ]
            .map(|(kind, name)| nodes.contains(&(kind.to_string(), name.to_string()))),
            nodes.iter().filter(|(kind, _)| kind == "effect").count(),
        ),
        ([true; 4], 4)
    );
    let trace = crate::syntax::unpack(&facts[2]);
    assert_eq!(trace["children"][0]["children"][0]["name"], "console.debug");
}

/// A guard around a body is one structure and the body it protects is one level deeper.
#[test]
fn a_guard_and_the_body_it_protects_are_one_structure_and_one_level() {
    let facts = facts_for(
        concat!(
            "export class Engine {\n",
            "  load(name: string): number {\n",
            "    try {\n",
            "      while (name.length) {\n",
            "        return 1;\n",
            "      }\n",
            "    } catch {\n",
            "      return 0;\n",
            "    }\n",
            "    return 2;\n",
            "  }\n",
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

    assert_eq!(increments, vec![("catch", 0), ("loop", 1)]);
    assert_eq!(facts[0]["name"], "load");
}

/// Reading the tree is what tells a type assertion apart from the keyword renaming an import.
#[test]
fn an_escape_hatch_is_read_from_the_tree_rather_than_from_the_word_as() {
    let facts = facts_for(
        concat!(
            "import { User as Person } from './models';\n",
            "export { Person as Account };\n",
            "// held as text rather than as an assertion\n",
            "const KINDS = ['json', 'toml'] as const;\n",
            "const said = 'a as b';\n",
            "const held = Person as unknown;\n",
            "const width = (held as any).length!;\n",
            "// @ts-expect-error the shape is checked elsewhere\n",
            "const total: any = width;\n",
        ),
        FactFamily("ModuleSurfaceFact"),
    );
    let hatches: Vec<(&str, i64)> = facts[0]["escape_hatches"]
        .as_array()
        .unwrap()
        .iter()
        .map(|held| {
            (
                held["kind"].as_str().unwrap_or_default(),
                held["line"].as_i64().unwrap_or_default(),
            )
        })
        .collect();

    assert_eq!(
        hatches,
        vec![
            ("assertion", 6),
            ("non_null", 7),
            ("assertion", 7),
            ("any", 7),
            ("ignore_comment", 8),
            ("any", 9),
        ]
    );
}

/// A declaration an export wraps generates exactly the JavaScript the bare one does.
#[test]
fn a_construct_stripping_cannot_erase_is_found_through_the_export_around_it() {
    let facts = facts_for(
        concat!(
            "export enum Status {\n  Active = 'ACTIVE',\n}\n",
            "enum Held {\n  Off = 'OFF',\n}\n",
            "export class Engine {\n  constructor(private limit: number) {}\n}\n",
        ),
        FactFamily("ModuleSurfaceFact"),
    );
    let found: Vec<(&str, &str)> = facts[0]["erasable_violations"]
        .as_array()
        .unwrap()
        .iter()
        .map(|held| {
            (
                held["kind"].as_str().unwrap_or_default(),
                held["name"].as_str().unwrap_or_default(),
            )
        })
        .collect();

    assert_eq!(
        found,
        vec![
            ("enum", "Status"),
            ("enum", "Held"),
            ("parameter_property", "limit"),
        ]
    );
}

/// A wholesale re-export names the module it republishes, and a climb names its specifier.
fn graph_of(sources: &[(&str, &str)]) -> crate::graph::Graph {
    let documents: Vec<Document> = sources
        .iter()
        .map(|(relative, source)| Document {
            relative: (*relative).to_string(),
            source: (*source).to_string(),
        })
        .collect();
    crate::graph::build("repo", &documents).expect("the graph builds")
}

/// Return every symbol node the graph holds, leaving the places on disk out of it.
fn symbols(graph: &crate::graph::Graph) -> Vec<String> {
    let mut found: Vec<String> = graph
        .nodes
        .iter()
        .filter(|node| !node.id.starts_with("path:"))
        .map(|node| node.id.clone())
        .collect();
    found.sort();
    found
}

/// Return every relation the graph states, leaving the containment of the tree out of it.
fn relations(graph: &crate::graph::Graph) -> Vec<String> {
    let mut found: Vec<String> = graph
        .edges
        .iter()
        .filter(|edge| edge.kind != EdgeKind::Contain)
        .map(|edge| format!("{} {:?} {}", edge.source, edge.kind, edge.target))
        .collect();
    found.sort();
    found.dedup();
    found
}

fn reaching(graph: &crate::graph::Graph, kind: EdgeKind) -> Vec<(&str, &str)> {
    let mut found: Vec<(&str, &str)> = graph
        .edges
        .iter()
        .filter(|edge| edge.kind == kind)
        .map(|edge| (edge.source.as_str(), edge.target.as_str()))
        .collect();
    found.sort_unstable();
    found.dedup();
    found
}

fn node_of<'a>(graph: &'a crate::graph::Graph, id: &str) -> &'a Node {
    graph
        .nodes
        .iter()
        .find(|node| node.id == id)
        .unwrap_or_else(|| panic!("the graph holds {id}"))
}

mod middle;
mod tail;
