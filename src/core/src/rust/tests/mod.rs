use super::*;
use crate::graph::{EdgeKind, NodeKind, ParameterKind};
use serde_json::json;

#[derive(Clone, Copy)]
struct FactFamily<'a>(&'a str);

fn facts_for(source: &str, family: FactFamily<'_>) -> Vec<Value> {
    let document = Document {
        relative: "src/engine.rs".to_string(),
        source: source.to_string(),
    };
    let mut facts = BTreeMap::from([(family.0.to_string(), Vec::new())]);
    extract(&document, &mut facts, &mut Stats::default());
    facts.remove(family.0).unwrap_or_default()
}

fn graph_of(source: &str) -> crate::graph::Graph {
    crate::graph::build(
        "repo",
        &[
            Document {
                relative: "kernel/src/main.rs".to_string(),
                source: "mod engine;\n".to_string(),
            },
            Document {
                relative: "kernel/src/engine.rs".to_string(),
                source: source.to_string(),
            },
        ],
    )
    .expect("the graph builds")
}

#[test]
fn pub_is_what_public_means_in_this_language() {
    let facts = facts_for(
        "pub fn build(name: &str) -> String { name.to_string() }\nfn helper() -> usize { 1 }\npub(crate) fn shared() -> usize { 2 }\n",
        FactFamily("FunctionFact"),
    );

    assert_eq!(facts[0]["name"], "build");
    assert_eq!(facts[0]["visibility"], "public");
    assert_eq!(facts[1]["visibility"], "private");
    assert_eq!(facts[2]["visibility"], "internal");
}

#[test]
fn external_binding_attributes_mark_declarations_as_framework_reached() {
    let graph =
        graph_of("#[pyclass]\npub struct Classifier;\n#[pyfunction]\npub fn classify() {}\n");
    let decorated: Vec<&str> = graph
        .nodes
        .iter()
        .filter(|node| !node.decorators.is_empty())
        .map(|node| node.qualname.rsplit("::").next().unwrap_or_default())
        .collect();

    assert_eq!(decorated, ["Classifier", "classify"]);
}

#[test]
fn parameters_keep_boolean_and_destructuring_evidence() {
    let facts = facts_for(
        "pub fn render(enabled: bool, (left, right): (usize, usize)) {}\n",
        FactFamily("FunctionFact"),
    );
    let parameters = facts[0]["parameters"].as_array().expect("parameters");

    assert_eq!(parameters[0]["name"], "enabled");
    assert_eq!(parameters[0]["type_name"], "bool");
    assert_eq!(parameters[0]["has_boolean_annotation"], true);
    assert_eq!(parameters[1]["name"], "(left, right)");
    assert_eq!(parameters[1]["type_name"], "(usize,usize)");
    assert!(
        parameters
            .iter()
            .all(|parameter| parameter["is_positional_only"] == true)
    );
    assert_eq!(
        facts[0]["definition"]["text"],
        "pub fn render(enabled: bool, (left, right): (usize, usize)) {}"
    );
}

#[test]
fn parameter_types_keep_generic_arguments_that_prevent_transposition() {
    let facts = facts_for(
        "fn resolve(definitions: &BTreeMap<String, usize>, reexports: &BTreeMap<String, String>) {}\n",
        FactFamily("FunctionFact"),
    );
    let parameters = facts[0]["parameters"].as_array().expect("parameters");

    assert_eq!(parameters[0]["type_name"], "&BTreeMap<String,usize>");
    assert_eq!(parameters[1]["type_name"], "&BTreeMap<String,String>");
}

#[test]
fn an_impl_block_carries_the_methods_of_the_type_it_names() {
    let facts = facts_for(
        "pub struct Engine { limit: usize }\n\nimpl Engine {\n    pub fn new() -> Self { Self { limit: 3 } }\n    fn run(&self) -> usize { self.limit }\n}\n\nimpl Default for Engine {\n    fn default() -> Self { Self::new() }\n}\n",
        FactFamily("ClassFact"),
    );
    let classes = facts[0]["classes"].as_array().unwrap();

    let methods = classes[0]["methods"].as_array().unwrap();
    assert_eq!(
        json!([
            classes[0]["name"],
            classes[0]["visibility"],
            classes[0]["field_count"],
            classes[0]["direct_bases"][0],
            methods[0]["kind"],
            methods[1]["kind"],
            methods[1]["visibility"],
            methods[0]["region"] == methods[1]["region"],
            methods[1]["region"] != methods[2]["region"],
        ]),
        json!([
            "Engine",
            "public",
            1,
            "Default",
            "static_method",
            "method",
            "private",
            true,
            true
        ])
    );
    assert!(
        classes[0]["source"]
            .as_str()
            .is_some_and(|source| source.starts_with("pub struct Engine"))
    );
    assert!(
        methods[0]["source"]
            .as_str()
            .is_some_and(|source| source.starts_with("pub fn new"))
    );
}

#[test]
fn a_use_tree_binds_every_name_its_groups_and_renames_hold() {
    let facts = facts_for(
        "use crate::source::{Source, Span as Range};\nuse serde_json::Value;\n\npub fn run(value: Value, span: Range, source: Source) {}\n",
        FactFamily("ImportBindingFact"),
    );
    let names: Vec<&str> = facts
        .iter()
        .map(|fact| fact["name"].as_str().unwrap_or_default())
        .collect();

    assert_eq!(names, vec!["Source", "Range", "Value"]);
    assert_eq!(facts[0]["module"], "crate::source");
    assert_eq!(facts[0]["is_project_owned"], true);
    assert_eq!(facts[2]["is_external"], true);
}

#[test]
fn a_module_counts_the_types_and_callables_it_declares() {
    let facts = facts_for(
        "pub struct One;\npub enum Two { A }\npub trait Three {}\npub fn run() {}\n",
        FactFamily("ModuleFact"),
    );

    assert_eq!(facts[0]["class_count"], 3);
    assert_eq!(facts[0]["function_count"], 1);
    assert_eq!(facts[0]["statement_count"], 4);
}

#[test]
fn a_crate_names_its_modules_from_the_directory_that_holds_its_root() {
    let graph = graph_of("pub struct Engine;\n");

    assert!(
        graph
            .nodes
            .iter()
            .any(|node| node.id == "rust:class:kernel::engine::Engine")
    );
}

#[test]
fn a_field_and_a_signature_state_the_types_they_depend_on() {
    let graph = graph_of(
        "pub struct Budget;\npub struct Tally;\npub struct Report;\npub struct Holder { limit: Budget }\n\npub fn run(count: Tally) -> Report { Report }\n",
    );
    let typed: Vec<&str> = graph
        .edges
        .iter()
        .filter(|edge| edge.kind == EdgeKind::Typed)
        .map(|edge| edge.target.as_str())
        .collect();

    assert!(typed.contains(&"rust:class:kernel::engine::Budget"));
    assert!(typed.contains(&"rust:class:kernel::engine::Tally"));
    assert!(typed.contains(&"rust:class:kernel::engine::Report"));
}

#[test]
fn every_parameter_this_language_takes_binds_by_position_and_carries_no_default() {
    let graph = graph_of("pub fn run(count: usize, label: &str) -> usize { count }\n");
    let stated: Vec<(&str, Option<ParameterKind>, bool)> = graph
        .nodes
        .iter()
        .filter(|node| node.kind == NodeKind::Parameter)
        .map(|node| {
            (
                node.qualname.as_str(),
                node.parameter_kind,
                node.has_default,
            )
        })
        .collect();

    assert_eq!(
        stated,
        vec![
            (
                "kernel::engine::run::count",
                Some(ParameterKind::PositionalOnly),
                false
            ),
            (
                "kernel::engine::run::label",
                Some(ParameterKind::PositionalOnly),
                false
            ),
        ]
    );
}

#[test]
fn a_trait_impl_inherits_the_trait_it_satisfies() {
    let graph = graph_of(
        "pub struct Engine;\npub trait Runner {}\n\nimpl Runner for Engine {\n    fn go(&self) {}\n}\n",
    );

    assert!(graph.edges.iter().any(|edge| edge.kind == EdgeKind::Inherit
        && edge.source == "rust:class:kernel::engine::Engine"
        && edge.target == "rust:class:kernel::engine::Runner"));
}

#[test]
fn a_call_and_a_construction_reach_what_this_crate_declares() {
    let graph = graph_of(
        "pub struct Engine { limit: usize }\n\npub fn helper() -> usize { 1 }\n\npub fn run() -> Engine {\n    let value = helper();\n    Engine { limit: value }\n}\n",
    );

    assert!(graph.edges.iter().any(|edge| edge.kind == EdgeKind::Call
        && edge.target == "rust:function:kernel::engine::helper"));
    assert!(
        graph
            .edges
            .iter()
            .any(|edge| edge.kind == EdgeKind::Instantiate
                && edge.target == "rust:class:kernel::engine::Engine")
    );
}

#[test]
fn an_annotation_states_every_position_it_names_a_lifetime_in() {
    let facts = facts_for(
        concat!(
            "pub fn only_inputs<'a>(left: &'a str, right: &'a str) -> usize { 0 }\n",
            "pub struct Holder { text: String }\n",
            "impl Holder {\n",
            "    pub fn name<'a>(&'a self, other: &str) -> &'a str { &self.text }\n",
            "    pub fn pick<'a>(&self, other: &'a str) -> &'a str { other }\n",
            "}\n",
            "pub fn from_one<'a>(node: Node<'a>, kind: &str) -> Option<&'a str> { None }\n",
            "pub fn streamed<'a>(items: impl Iterator<Item = &'a str>) -> usize { 0 }\n",
        ),
        FactFamily("RustSurfaceFact"),
    );
    let placed: Vec<&Value> = facts[0]["annotations"].as_array().unwrap().iter().collect();

    assert_eq!(
        json!([
            placed[0]["owner"],
            placed[0]["returned"].as_array().unwrap().is_empty(),
            placed[1]["owner"],
            placed[1]["receiver"],
            placed[1]["returned"][0],
            placed[1]["parameters"].as_array().unwrap().is_empty(),
            placed[2]["owner"],
            placed[2]["receiver"],
            placed[2]["parameters"][0],
            placed[3]["owner"],
            placed[3]["receiver"],
            placed[3]["returned"][0],
            placed[4]["owner"],
            placed[4]["required_by_syntax"][0],
        ]),
        json!([
            "only_inputs",
            true,
            "name",
            "a",
            "a",
            true,
            "pick",
            "",
            "a",
            "from_one",
            "",
            "a",
            "streamed",
            "a"
        ])
    );
}

#[test]
fn a_pinned_reference_is_told_apart_from_a_bound_and_a_copy_from_a_loop() {
    let facts = facts_for(
        concat!(
            "pub struct Report { title: &'static str }\n",
            "pub fn spawn<T: Send + 'static>(value: T) {}\n",
            "pub fn run(items: Vec<String>, prefix: String) -> Vec<String> {\n",
            "    let owned = prefix.clone();\n",
            "    for item in items {\n",
            "        registry.insert(prefix.clone(), item);\n",
            "    }\n",
            "    Vec::new()\n",
            "}\n",
        ),
        FactFamily("RustSurfaceFact"),
    );
    let pins = facts[0]["pins"].as_array().unwrap();
    let clones = facts[0]["clones"].as_array().unwrap();

    assert_eq!(
        json!([
            pins.len(),
            pins.iter()
                .filter(|pin| pin["position"] == "demand")
                .count(),
            pins[0]["position"],
            clones.len(),
            clones[0]["loop_depth"],
            clones[1]["loop_depth"],
            clones[1]["receiver"],
            clones[1]["owner"],
        ]),
        json!([2, 1, "demand", 2, 0, 1, "prefix", "run::"])
    );
}

#[test]
fn a_pin_demands_in_a_parameter_and_only_promises_in_a_return() {
    let facts = facts_for(
        concat!(
            "pub fn label(kind: usize) -> &'static str { \"rust\" }\n",
            "pub fn describe(name: &'static str) -> usize { name.len() }\n",
        ),
        FactFamily("RustSurfaceFact"),
    );
    let pins = facts[0]["pins"].as_array().unwrap();

    assert_eq!(pins.len(), 2);
    assert_eq!(pins[0]["position"], "supply");
    assert_eq!(pins[1]["position"], "demand");
}

#[test]
fn a_path_climbs_the_way_the_module_reading_it_would() {
    let nested = crate::discovery::Document {
        relative: "kernel/src/graph/walk.rs".to_string(),
        source: String::new(),
    };
    let collector = Collector::new(Source::new(&nested), "kernel::graph::walk".to_string());

    assert_eq!(collector.absolute("crate::source"), "kernel::source");
    assert_eq!(
        collector.absolute("self::inner"),
        "kernel::graph::walk::inner"
    );
    assert_eq!(
        collector.absolute("super::builder"),
        "kernel::graph::builder"
    );
    assert_eq!(collector.absolute("serde_json::Value"), "serde_json::Value");

    let root_document = crate::discovery::Document {
        relative: "kernel/src/lib.rs".to_string(),
        source: String::new(),
    };
    let root = Collector::new(Source::new(&root_document), "kernel".to_string());
    assert_eq!(root.absolute("super::builder"), "super::builder");
}

mod continuation;
