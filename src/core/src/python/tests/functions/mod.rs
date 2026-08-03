use super::*;

fn function_named(source: &str, name: FactName) -> Value {
    facts_for(source, FactFamily("FunctionFact"))
        .into_iter()
        .find(|fact| fact["name"] == name.0)
        .expect("the callable is declared")
}

#[test]
fn implementation_lines_leave_documentation_comments_and_blanks_out() {
    let source = concat!(
        "def read(value):\n",
        "    \"\"\"Explain this callable across\n",
        "    several lines without making it longer.\n",
        "    \"\"\"\n",
        "    prepared = value.strip()\n",
        "\n",
        "    # The explanation between statements is not work either.\n",
        "    return prepared\n",
    );

    assert_eq!(
        function_named(source, FactName("read"))["implementation_lines"],
        2
    );
}

#[test]
fn a_rule_decorator_marks_one_declarative_query_body() {
    let source = "@rule(\"EXAMPLE\")\ndef query(subject):\n    return subject.lazy(\"facts\")\n";

    assert_eq!(
        function_named(source, FactName("query"))["is_declarative_body"],
        true
    );
}

#[test]
fn a_straight_lazy_frame_builder_is_declarative_but_host_branching_is_not() {
    let source = concat!(
        "def projected(table) -> pl.LazyFrame:\n",
        "    facts = table.lazy(\"facts\")\n",
        "    return facts.select(\"name\")\n\n",
        "def selected(table, enabled) -> pl.LazyFrame:\n",
        "    if enabled:\n",
        "        return table.lazy(\"enabled\")\n",
        "    return table.lazy(\"disabled\")\n",
    );

    assert_eq!(
        function_named(source, FactName("projected"))["is_declarative_body"],
        true
    );
    assert_eq!(
        function_named(source, FactName("selected"))["is_declarative_body"],
        false
    );
}

#[test]
fn a_decorator_says_what_binds_a_member_and_who_calls_it() {
    let source = concat!(
        "import functools\n",
        "from typing import overload, override\n\n\n",
        "class Engine(Protocol):\n",
        "    @property\n",
        "    def size(self):\n",
        "        return 1\n\n",
        "    @functools.cache\n",
        "    def parse(self, text):\n",
        "        return text\n\n",
        "    @overload\n",
        "    def read(self, first): ...\n\n",
        "    @override\n",
        "    def run(self):\n",
        "        return 2\n\n",
        "    @app.route(\"/health\")\n",
        "    def health(self):\n",
        "        return 3\n",
    );

    assert_eq!(
        function_named(source, FactName("size"))["is_property"],
        true
    );
    assert_eq!(
        function_named(source, FactName("size"))["cache_decorator"],
        ""
    );
    assert_eq!(
        function_named(source, FactName("parse"))["cache_decorator"],
        "cache"
    );
    assert_eq!(
        function_named(source, FactName("parse"))["is_property"],
        false
    );
    assert_eq!(
        function_named(source, FactName("read"))["is_overload"],
        true
    );
    assert_eq!(
        function_named(source, FactName("run"))["is_polymorphic"],
        true
    );
    assert_eq!(
        function_named(source, FactName("run"))["is_framework_hook"],
        false
    );
    assert_eq!(
        function_named(source, FactName("health"))["is_framework_hook"],
        true
    );
    assert_eq!(
        function_named(source, FactName("size"))["is_protocol_member"],
        true
    );
}

#[test]
fn a_body_states_what_it_reads_calls_and_hands_back() {
    let source = concat!(
        "def normalize(value):\n",
        "    return underscore(value)\n\n\n",
        "def walk(node):\n",
        "    return walk(node.parent)\n\n\n",
        "class Client:\n",
        "    def size(self):\n",
        "        return len(self.rows)\n\n",
        "    def build(self):\n",
        "        return Client()\n",
    );

    assert_eq!(
        function_named(source, FactName("normalize"))["returns_single_call"],
        true
    );
    assert_eq!(
        function_named(source, FactName("normalize"))["forwards_only_parameter_unchanged"],
        true
    );
    assert_eq!(
        function_named(source, FactName("normalize"))["behavior_operation_count"],
        1
    );
    assert_eq!(
        function_named(source, FactName("walk"))["is_recursive"],
        true
    );
    assert_eq!(
        function_named(source, FactName("walk"))["forwards_only_parameter_unchanged"],
        false
    );
    assert_eq!(
        function_named(source, FactName("size"))["reads_receiver"],
        true
    );
    assert_eq!(
        function_named(source, FactName("build"))["reads_receiver"],
        false
    );
}

#[test]
fn a_helper_one_method_calls_names_the_class_that_owns_it() {
    let source = concat!(
        "def parse(text):\n",
        "    return text.strip()\n\n\n",
        "def widen(text):\n",
        "    return text.upper()\n\n\n",
        "class Client:\n",
        "    def read(self, text):\n",
        "        return parse(text)\n\n\n",
        "handler = widen\n",
    );

    assert_eq!(
        function_named(source, FactName("parse"))["sole_reference_owner_class"],
        "Client"
    );
    assert_eq!(
        function_named(source, FactName("parse"))["sole_reference_owner_definition"]["text"],
        "def read(self, text):\n        return parse(text)"
    );
    assert_eq!(
        function_named(source, FactName("parse"))["is_first_class_reference"],
        false
    );
    assert_eq!(
        function_named(source, FactName("widen"))["sole_reference_owner_class"],
        ""
    );
    assert_eq!(
        function_named(source, FactName("widen"))["is_first_class_reference"],
        true
    );
    assert_eq!(
        function_named(source, FactName("widen"))["reference_count"],
        1
    );
}

#[test]
fn a_factory_reproducing_field_validation_states_all_three_halves_of_that() {
    let source = concat!(
        "class Order(BaseModel):\n",
        "    @classmethod\n",
        "    def from_table(cls, rows):\n",
        "        if not isinstance(rows, list):\n",
        "            raise ValueError(rows)\n",
        "        return cls(rows=rows)\n\n",
        "    @field_validator(\"rows\")\n",
        "    @classmethod\n",
        "    def check(cls, value):\n",
        "        return value\n",
    );
    let factory = function_named(source, FactName("from_table"));

    assert_eq!(factory["is_model_method"], true);
    assert_eq!(factory["is_pydantic_validator"], false);
    assert_eq!(factory["checks_raw_input_type"], true);
    assert_eq!(factory["raises_validation_exception"], true);
    assert_eq!(factory["constructs_owner_model"], true);
    assert_eq!(
        function_named(source, FactName("check"))["is_pydantic_validator"],
        true
    );
}

#[test]
fn only_the_asyncio_this_file_imported_counts_as_scheduling_work() {
    let scheduled = concat!(
        "import asyncio\n\n\n",
        "async def run(items):\n",
        "    first = asyncio.create_task(load(items))\n",
        "    second = asyncio.create_task(save(items))\n",
        "    return await asyncio.gather(first, second)\n",
    );
    let named = concat!(
        "def create_task(subject):\n",
        "    return subject\n\n\n",
        "def create_all_tasks():\n",
        "    return [create_task(name) for name in NAMES]\n",
    );

    assert_eq!(
        function_named(scheduled, FactName("run"))["created_task_count"],
        2
    );
    assert_eq!(
        function_named(scheduled, FactName("run"))["gather_consumes_created_tasks"],
        true
    );
    assert_eq!(
        function_named(scheduled, FactName("run"))["gather_returns_exceptions"],
        false
    );
    assert_eq!(
        function_named(named, FactName("create_all_tasks"))["created_task_count"],
        0
    );
}

#[test]
fn a_gather_told_to_hand_failures_back_is_not_a_task_group_candidate() {
    let source = concat!(
        "import asyncio\n\n\n",
        "async def run(items):\n",
        "    async with asyncio.TaskGroup() as group:\n",
        "        held = [asyncio.create_task(load(item)) for item in items]\n",
        "    return await asyncio.gather(*held, return_exceptions=True)\n",
    );
    let found = function_named(source, FactName("run"));

    assert_eq!(found["has_task_group"], true);
    assert_eq!(found["gather_returns_exceptions"], true);
}

#[test]
fn a_tensor_signature_states_its_roles_and_what_the_docstring_settled() {
    let bare = concat!(
        "def normalize(values: torch.Tensor) -> torch.Tensor:\n",
        "    \"\"\"Normalize values.\"\"\"\n",
        "    return values\n",
    );
    let told = concat!(
        "def normalize(values: torch.Tensor) -> torch.Tensor:\n",
        "    \"\"\"Normalize a float32 tensor with shape [batch, features].\"\"\"\n",
        "    return values\n",
    );
    let typed = concat!(
        "def scale(values: Float32[Tensor, \"batch features\"]) -> int:\n",
        "    return 1\n",
    );

    assert_eq!(
        function_named(bare, FactName("normalize"))["recognized_tensor_roles"],
        json!(["values", "return"])
    );
    assert_eq!(
        function_named(bare, FactName("normalize"))["has_tensor_shape_semantics"],
        false
    );
    assert_eq!(
        function_named(told, FactName("normalize"))["has_tensor_shape_semantics"],
        true
    );
    assert_eq!(
        function_named(told, FactName("normalize"))["has_tensor_dtype_semantics"],
        true
    );
    assert_eq!(
        function_named(typed, FactName("scale"))["has_tensor_shape_semantics"],
        true
    );
    assert_eq!(
        function_named(typed, FactName("scale"))["has_tensor_dtype_semantics"],
        true
    );
}

#[test]
fn a_default_says_whether_a_caller_reads_a_flag_at_the_call_site() {
    let facts = facts_for(
        concat!(
            "def render(source: Table[Call], subject: Table[Function], ",
            "inline: bool = True, width: int = 80):\n",
            "    return 1\n",
        ),
        FactFamily("FunctionFact"),
    );
    let parameters = facts[0]["parameters"].as_array().expect("a list");

    assert_eq!(parameters[0]["type_name"], "Table[Call]");
    assert_eq!(parameters[1]["type_name"], "Table[Function]");
    assert_eq!(parameters[2]["has_boolean_default"], true);
    assert_eq!(parameters[3]["has_boolean_default"], false);
}
