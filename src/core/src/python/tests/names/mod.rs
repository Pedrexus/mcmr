use super::*;

#[test]
fn import_bindings_carry_their_references_and_origin() {
    let facts = facts_for(
        concat!(
            "import json\n",
            "from . import models\n",
            "from .constants import _DEFAULT_TIMEOUT, _helper\n",
            "print(json.dumps(1))\n",
        ),
        FactFamily("ImportBindingFact"),
    );
    assert_eq!(
        json!([
            facts.len(),
            facts[0]["name"],
            facts[0]["reference_count"],
            facts[0]["is_relative"],
            facts[0]["binding"]["text"],
            facts[0]["module_node"]["text"],
            facts[1]["name"],
            facts[1]["reference_count"],
            facts[1]["is_relative"],
            facts[1]["is_sole_binding"],
            facts[2]["is_private_member"],
            facts[2]["is_private_uppercase_constant"],
            facts[3]["is_private_member"],
            facts[3]["is_private_uppercase_constant"],
            facts[2]["module_node"]["text"],
        ]),
        json!([
            4,
            "json",
            1,
            false,
            "json",
            "json",
            "models",
            0,
            true,
            true,
            true,
            true,
            true,
            false,
            "constants"
        ])
    );
}

#[test]
fn type_only_relative_imports_retain_exact_reference_nodes() {
    let model = binding_named(
        concat!(
            "from typing import TYPE_CHECKING\n",
            "if TYPE_CHECKING:\n",
            "    from ..models import Model\n",
            "def build(value: Model) -> Model:\n",
            "    return value\n",
        ),
        FactName("Model"),
    );

    assert_eq!(
        json!([
            model["is_type_only"],
            model["relative_level"],
            model["reference_count"],
            model["references"].as_array().map(Vec::len),
            model["references"][0]["text"],
            model["references"][1]["text"],
        ]),
        json!([true, 2, 2, 2, "Model", "Model"])
    );
}

fn binding_named(source: &str, name: FactName) -> Value {
    facts_for(source, FactFamily("ImportBindingFact"))
        .into_iter()
        .find(|fact| fact["name"] == name.0)
        .expect("the name is bound by an import")
}

#[test]
fn a_name_is_read_wherever_the_interpreter_would_read_it() {
    let source = concat!(
        "import json\n",
        "import math\n",
        "import re\n",
        "import textwrap\n",
        "import unicodedata\n\n\n",
        "def run(value):\n",
        "    if value == 1:\n",
        "        return 0\n",
        "    elif isinstance(value, json.JSONDecoder):\n",
        "        return 1\n",
        "    try:\n",
        "        del textwrap.cache\n",
        "    except math.error as failure:\n",
        "        raise unicodedata.UnicodeError from failure\n",
        "    match value:\n",
        "        case re.Match():\n",
        "            return 3\n",
        "    return 4\n",
    );

    for name in ["json", "math", "re", "textwrap", "unicodedata"] {
        assert_eq!(
            binding_named(source, FactName(name))["reference_count"],
            1,
            "{name}"
        );
    }
}

#[test]
fn a_forward_reference_written_as_a_string_reads_the_name_it_spells() {
    let source = concat!(
        "from typing import Annotated, Literal, Optional\n",
        "from decimal import Decimal\n",
        "from fractions import Fraction\n",
        "from numbers import Number\n",
        "from pathlib import Path\n",
        "from uuid import UUID\n\n",
        "Alias = Optional[\"Decimal\"]\n",
        "Deep = dict[str, \"Fraction\"]\n",
        "Valued = Literal[\"Number\"]\n",
        "Tagged = Annotated[int, \"Path\"]\n",
        "type Money = \"UUID\"\n",
    );

    assert_eq!(
        binding_named(source, FactName("Decimal"))["reference_count"],
        1
    );
    assert_eq!(
        binding_named(source, FactName("Fraction"))["reference_count"],
        1
    );
    assert_eq!(
        binding_named(source, FactName("UUID"))["reference_count"],
        1
    );
    assert_eq!(
        binding_named(source, FactName("Number"))["reference_count"],
        0
    );
    assert_eq!(
        binding_named(source, FactName("Path"))["reference_count"],
        0
    );
}

#[test]
fn a_typing_constructor_states_its_types_as_text_and_they_are_read_as_types() {
    let source = concat!(
        "from typing import TypeVar, cast\n",
        "from decimal import Decimal\n",
        "from fractions import Fraction\n",
        "from uuid import UUID\n\n",
        "Number = TypeVar(\"Number\", int, \"Decimal\")\n",
        "def run(value):\n",
        "    return cast(\"list[Fraction]\", value)\n",
        "def carry(value):\n",
        "    return str(\"UUID\")\n",
    );

    assert_eq!(
        binding_named(source, FactName("Decimal"))["reference_count"],
        1
    );
    assert_eq!(
        binding_named(source, FactName("Fraction"))["reference_count"],
        1
    );
    assert_eq!(
        binding_named(source, FactName("UUID"))["reference_count"],
        0
    );
}

#[test]
fn a_name_the_module_binds_again_is_one_no_deletion_repairs() {
    let source = concat!(
        "from typing import TYPE_CHECKING\n",
        "if TYPE_CHECKING:\n",
        "    from decimal import Decimal\n",
        "else:\n",
        "    Decimal = None\n",
        "from fractions import Fraction\n",
    );

    assert_eq!(
        binding_named(source, FactName("Decimal"))["reference_count"],
        1
    );
    assert_eq!(
        binding_named(source, FactName("Decimal"))["has_qualifying_use"],
        true
    );
    assert_eq!(
        binding_named(source, FactName("Fraction"))["reference_count"],
        0
    );
}

#[test]
fn an_import_under_a_failure_guard_is_there_for_whether_it_succeeds() {
    let source = concat!(
        "try:\n",
        "    import h2\n",
        "except ImportError:\n",
        "    import tomli\n",
        "try:\n",
        "    import socksio\n",
        "except ValueError:\n",
        "    pass\n",
    );

    assert_eq!(
        binding_named(source, FactName("h2"))["has_documented_side_effect"],
        true
    );
    assert_eq!(
        binding_named(source, FactName("tomli"))["has_documented_side_effect"],
        false
    );
    assert_eq!(
        binding_named(source, FactName("socksio"))["has_documented_side_effect"],
        false
    );
}

#[test]
fn a_statement_binding_several_names_addresses_each_binding_separately() {
    let source = "from json import dumps, loads\nimport math\n";

    assert_eq!(
        json!([
            binding_named(source, FactName("dumps"))["is_sole_binding"],
            binding_named(source, FactName("dumps"))["binding"]["text"],
        ]),
        json!([false, "dumps"])
    );
    assert_eq!(
        binding_named(source, FactName("loads"))["is_sole_binding"],
        false
    );
    assert_eq!(
        binding_named(source, FactName("math"))["is_sole_binding"],
        true
    );
}

#[test]
fn a_public_surface_is_read_however_the_module_builds_it() {
    let source = concat!(
        "from .api import Client\n",
        "from .engine import Engine\n",
        "from .errors import Failure\n",
        "from .ports import Port\n",
        "__all__ = [\"Client\"]\n",
        "__all__ += [\"Engine\"]\n",
        "if True:\n",
        "    __all__ = [*__all__, \"Failure\"]\n",
    );

    for name in ["Client", "Engine", "Failure"] {
        assert_eq!(
            binding_named(source, FactName(name))["is_reexported"],
            true,
            "{name}"
        );
    }
    assert_eq!(
        binding_named(source, FactName("Port"))["is_reexported"],
        false
    );
}

#[test]
fn local_dunder_all_does_not_declare_a_module_surface() {
    let source = concat!(
        "from .api import Client\n",
        "def names():\n",
        "    __all__ = ['Client']\n",
        "    return __all__\n",
    );

    assert_eq!(
        binding_named(source, FactName("Client"))["is_reexported"],
        false
    );
    assert_eq!(
        facts_for(source, FactFamily("ModuleFact"))[0]["declares_all"],
        false
    );
}

#[test]
fn module_facts_distinguish_executable_content_and_declaration_kinds() {
    let facts = facts_for_path(
        RelativePath("package/__init__.py"),
        concat!(
            "\"\"\"Package docs.\"\"\"\n",
            "from .client import Client\n",
            "__all__: list[str] = ['Client']\n",
            "class Local:\n    pass\n",
            "def connect():\n    pass\n",
            "def __getattr__(name):\n    return Client\n",
        ),
        FactFamily("ModuleFact"),
    );
    let fact = &facts[0];
    let members = fact["members"].as_array().expect("module members");

    assert_eq!(
        json!([
            fact["executable_statement_count"],
            fact["declares_all"],
            fact["all_declarations"][0]["text"],
            fact["is_package_initializer"],
            members[0]["kind"],
            members[1]["kind"],
            members[2]["kind"],
        ]),
        json!([
            5,
            true,
            "__all__: list[str] = ['Client']",
            true,
            "class",
            "function",
            "function"
        ])
    );

    let empty = facts_for_path(
        RelativePath("package/__init__.py"),
        "\"\"\"Package docs.\"\"\"\n",
        FactFamily("ModuleFact"),
    );
    assert_eq!(empty[0]["executable_statement_count"], 0);
}
