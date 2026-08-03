use super::*;

#[test]
fn a_class_states_its_keywords_its_registry_key_and_the_regions_it_holds() {
    let source = concat!(
        "class Engine(Base, metaclass=Meta):\n",
        "    name = \"engine\"\n\n",
        "    def open(self):\n",
        "        return 1\n\n",
        "    # region reading\n",
        "    def read(self):\n",
        "        return 2\n",
    );
    let held = &facts_for(source, FactFamily("ClassFact"))[0]["classes"][0];

    assert_eq!(held["class_keywords"], json!(["metaclass=Meta"]));
    assert_eq!(held["has_explicit_registry_name"], true);
    assert_eq!(held["methods"][0]["region"], 0);
    assert_eq!(held["methods"][1]["region"], 1);
    assert_eq!(held["span"]["start_line"], 1);
    assert_eq!(held["span"]["end_line"], 9);
}

#[test]
fn a_class_knows_when_a_test_runner_owns_its_file() {
    let facts = facts_for_path(
        RelativePath("tests/test_tools.py"),
        "class TestTools:\n    def test_open(self):\n        pass\n",
        FactFamily("ClassFact"),
    );

    assert_eq!(facts[0]["classes"][0]["is_test"], true);
}

#[test]
fn a_typing_protocol_states_that_it_has_no_runtime_implementation_surface() {
    let source = concat!(
        "from typing import Protocol as Contract\n",
        "import typing_extensions\n\n",
        "class _Direct(Contract):\n    pass\n\n",
        "class _Qualified(typing_extensions.Protocol):\n    pass\n\n",
        "class _Runtime:\n    pass\n",
    );
    let facts = facts_for(source, FactFamily("ClassFact"));
    let classes = facts[0]["classes"].as_array().expect("a class list");

    assert_eq!(classes[0]["is_protocol"], true);
    assert_eq!(classes[1]["is_protocol"], true);
    assert_eq!(classes[2]["is_protocol"], false);
}

#[test]
fn a_layer_adding_only_a_name_or_a_forwarding_frame_states_that_it_passes_through() {
    let empty = facts_for(
        "class Json(Serializer):\n    pass\n",
        FactFamily("ClassFact"),
    );
    let forwarding = facts_for(
        "class Named(Parser):\n    def parse(self, text, *rest, strict=False):\n        return super().parse(text, *rest, strict=strict)\n",
        FactFamily("ClassFact"),
    );
    let real = facts_for(
        "class Json(Serializer):\n    def encode(self, value):\n        return dumps(value)\n",
        FactFamily("ClassFact"),
    );

    assert_eq!(empty[0]["classes"][0]["is_pass_through_layer"], true);
    assert_eq!(forwarding[0]["classes"][0]["is_pass_through_layer"], true);
    assert_eq!(real[0]["classes"][0]["is_pass_through_layer"], false);
}

#[test]
fn a_field_copied_off_a_component_the_owner_already_keeps_is_counted_once() {
    let source = concat!(
        "class Report:\n",
        "    def __init__(self, document, width):\n",
        "        self.document = document\n",
        "        self.path = document.path\n",
        "        self.title = normalize(document.title)\n",
        "        self.width = width\n",
    );

    assert_eq!(
        facts_for(source, FactFamily("ClassFact"))[0]["classes"][0]["duplicate_component_alias_count"],
        1
    );
}

#[test]
fn a_static_method_calling_a_sibling_through_the_owner_name_states_that_call() {
    let source = concat!(
        "class Parser:\n",
        "    @classmethod\n",
        "    def from_text(cls, text):\n",
        "        return cls()\n\n",
        "    @staticmethod\n",
        "    def decide(text):\n",
        "        return Parser.from_text(text)\n",
    );
    let methods = facts_for(source, FactFamily("ClassFact"))[0]["classes"][0]["methods"].clone();

    assert_eq!(
        methods[1]["owner_qualified_calls"],
        json!(["Parser.from_text"])
    );
    assert_eq!(methods[0]["owner_qualified_calls"], json!([] as [&str; 0]));
}

#[test]
fn a_structure_repeating_the_fields_of_one_object_states_its_keys_beside_them() {
    let source = concat!(
        "def render(definition):\n",
        "    return {\n",
        "        \"id\": definition.id,\n",
        "        \"summary\": definition.summary,\n",
        "        \"scope\": definition.scope,\n",
        "        \"lane\": definition.lane,\n",
        "    }\n",
    );
    let groups = facts_for(source, FactFamily("ClassFact"))[0]["projection_groups"].clone();

    assert_eq!(groups[0]["root"], "definition");
    assert_eq!(
        groups[0]["attribute_names"],
        json!(["id", "summary", "scope", "lane"])
    );
    assert_eq!(
        groups[0]["output_keys"],
        json!(["id", "summary", "scope", "lane"])
    );
}

#[test]
fn control_increments_record_their_nesting_depth() {
    let facts = facts_for(
        "def run(items):\n    for item in items:\n        if item:\n            break\n",
        FactFamily("FunctionFact"),
    );
    let increments = facts[0]["control_increments"].as_array().unwrap();
    assert_eq!(increments.len(), 3);
    assert_eq!(increments[0]["kind"], "loop");
    assert_eq!(increments[0]["nesting_depth"], 0);
    assert_eq!(increments[1]["kind"], "conditional");
    assert_eq!(increments[1]["nesting_depth"], 1);
    assert_eq!(increments[2]["kind"], "jump");
    assert_eq!(increments[2]["nesting_depth"], 2);
}

#[test]
fn classes_carry_members_with_their_kind_and_visibility() {
    let facts = facts_for(
        "from functools import cached_property\nfrom typing import ClassVar\n\n\nclass Engine:\n    limit: int = 3\n    kind: ClassVar[str] = \"engine\"\n    name = \"default\"\n\n    def __init__(self):\n        pass\n\n    @property\n    def _state(self):\n        return 1\n\n    @cached_property\n    def value(self):\n        return 2\n",
        FactFamily("ClassFact"),
    );
    let classes = facts[0]["classes"].as_array().unwrap();
    let methods = classes[0]["methods"].as_array().unwrap();
    assert_eq!(
        json!([
            classes[0]["name"],
            classes[0]["field_count"],
            methods[0]["kind"],
            methods[1]["kind"],
            methods[1]["visibility"],
            methods[2]["kind"],
            methods[2]["visibility"],
        ]),
        json!([
            "Engine",
            1,
            "constructor",
            "property",
            "protected",
            "property",
            "public"
        ])
    );
    assert!(
        classes[0]["source"]
            .as_str()
            .is_some_and(|source| source.starts_with("class Engine"))
    );
    assert!(
        methods[0]["source"]
            .as_str()
            .is_some_and(|source| source.starts_with("def __init__"))
    );
}

#[test]
fn calls_resolve_their_name_receiver_and_discarded_result() {
    let facts = facts_for(
        "import shutil\nshutil.rmtree(path)\nvalue = len(items)\n",
        FactFamily("CallFact"),
    );
    let calls = facts[0]["calls"].as_array().unwrap();
    assert_eq!(calls[0]["qualified_name"], "shutil.rmtree");
    assert_eq!(calls[0]["result_is_discarded"], true);
    assert_eq!(calls[0]["receiver"]["text"], "shutil");
    assert_eq!(calls[1]["qualified_name"], "len");
    assert!(calls[1].get("result_is_discarded").is_none());
}

#[test]
fn constants_carry_the_statements_between_them_and_their_valid_anchor() {
    let facts = facts_for(
        concat!(
            "\"\"\"Module docs.\"\"\"\n",
            "import json\n\n",
            "class Service:\n",
            "    pass\n\n",
            "LATE = 3\n",
            "base = make_base()\n",
            "DERIVED = base + 1\n",
            "NEXT = DERIVED + 1\n",
        ),
        FactFamily("ModuleFact"),
    );
    let placements = facts[0]["constant_placements"].as_array().unwrap();
    let members = facts[0]["members"].as_array().unwrap();

    assert_eq!(placements[0]["name"], "LATE");
    assert_eq!(placements[0]["intervening_statement_count"], 1);
    assert_eq!(placements[1]["name"], "DERIVED");
    assert_eq!(placements[1]["intervening_statement_count"], 0);
    assert_eq!(placements[2]["intervening_statement_count"], 0);
    assert!(
        members[0]["source"]
            .as_str()
            .is_some_and(|source| source.starts_with("class Service"))
    );
}

#[test]
fn typing_and_pytest_module_configuration_stay_with_imports_before_constants() {
    let facts = facts_for(
        concat!(
            "from typing import TYPE_CHECKING\n",
            "import pytest\n\n",
            "if TYPE_CHECKING:\n",
            "    from pathlib import Path\n\n",
            "pytestmark = pytest.mark.integration\n",
            "ROOT = 'project'\n",
        ),
        FactFamily("ModuleFact"),
    );
    let placements = facts[0]["constant_placements"].as_array().unwrap();

    assert_eq!(placements[0]["name"], "ROOT");
    assert_eq!(placements[0]["intervening_statement_count"], 0);
}

#[test]
fn explicit_flaky_markers_carry_their_quarantine_lifecycle() {
    let facts = facts_for_path(
        RelativePath("test_example.py"),
        concat!(
            "import pytest\n\n",
            "@pytest.mark.flaky(\n",
            "    since='2020-01-01',\n",
            "    owner='testing',\n",
            "    remediation='https://example.com/issues/1',\n",
            "    recurred_after_repair=True,\n",
            ")\n",
            "def test_unstable():\n",
            "    pass\n",
        ),
        FactFamily("TestFunctionFact"),
    );
    let quarantines = facts[0]["quarantined_tests"].as_array().unwrap();

    assert_eq!(quarantines.len(), 1);
    assert_eq!(quarantines[0]["name"], "test_unstable");
    assert!(quarantines[0]["age_days"].as_u64().unwrap() > 14);
    assert_eq!(quarantines[0]["owner"], "testing");
    assert_eq!(quarantines[0]["has_remediation_evidence"], true);
    assert_eq!(quarantines[0]["recurred_after_repair"], true);
}

#[test]
fn calls_carry_assignment_async_decorator_star_and_boolean_syntax() {
    let facts = facts_for(
        concat!(
            "@decorate(option=True)\n",
            "async def run(flag: bool):\n",
            "    answer = bool(not flag)\n",
            "    return submit(*items)\n",
        ),
        FactFamily("CallFact"),
    );
    let calls = facts[0]["calls"].as_array().unwrap();

    assert_eq!(calls[0]["is_decorator_factory"], true);
    assert_eq!(calls[1]["assigned_target"], "answer");
    assert_eq!(calls[1]["enclosing_is_async"], true);
    assert_eq!(calls[1]["arguments"][0]["resolved_type"], "bool");
    assert_eq!(calls[2]["has_starred_arguments"], true);
}

#[test]
fn call_resolution_declines_shadowed_names_and_ambiguous_import_aliases() {
    let facts = facts_for(
        concat!(
            "import first as shared\n",
            "import second as shared\n\n",
            "def run(tuple):\n",
            "    tuple(items)\n",
            "    shared.convert(value)\n",
        ),
        FactFamily("CallFact"),
    );
    let calls = facts[0]["calls"].as_array().unwrap();

    assert_eq!(calls[0]["is_shadowed"], true);
    assert_eq!(calls[1]["has_ambiguous_alias"], true);
}

#[test]
fn comment_groups_separate_directives_from_commented_out_code() {
    let facts = facts_for(
        "# noqa: E501\nvalue = 1\n# total = compute(value)\n# print(total)\n\n# a real sentence\n",
        FactFamily("CommentFact"),
    );
    let groups = facts[0]["groups"].as_array().unwrap();
    assert_eq!(groups[0]["is_directive"], true);
    assert_eq!(groups[0]["parses_as_source"], false);
    assert_eq!(groups[1]["line_count"], 2);
    assert_eq!(groups[1]["parses_as_source"], true);
    assert_eq!(groups[2]["line_count"], 1);
    assert_eq!(groups[2]["parses_as_source"], false);
}

#[test]
fn a_waiver_is_read_only_from_a_comment_token() {
    let facts = facts_for(
        "def run():\n    label = '# noqa'\n    value = work()  # noqa: PERF401 reason=measured\n",
        FactFamily("WaiverFact"),
    );
    let waivers = facts[0]["waivers"].as_array().unwrap();

    assert_eq!(waivers.len(), 1);
    assert_eq!(waivers[0]["metadata"]["reason"], "measured");
}
