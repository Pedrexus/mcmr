import sys
from importlib.metadata import EntryPoint
from types import FunctionType, ModuleType
from typing import Annotated, get_type_hints

import pytest
from pydantic import ValidationError

from mcmr import Category, rule
from mcmr.domain.contracts import RuleContract, RuleLane, RuleScope
from mcmr.facts import ImportBindingFact
from mcmr.query import OccurrenceQuery
from mcmr.rulebook.catalog import Catalog
from mcmr.rulebook.discovery import RuleModuleDiscovery
from mcmr.rules.general import module_cohesion
from mcmr.rules.python import unused_import
from mcmr.table import Table


def module_with(name: str, **members: RuleContract) -> ModuleType:
    """Create one synthetic rule module for catalog tests."""
    module = ModuleType(name)
    module.__dict__.update(members)
    return module


def test_catalog_derives_identity_and_complete_documentation() -> None:
    catalog = Catalog(modules=[module_with(unused_import.module, unused_import=unused_import)])
    definition = catalog.definition(unused_import)

    assert definition.id == "PY-IMPO0003"
    assert definition.lane == "deterministic"
    assert definition.fact == "ImportBindingFact"
    assert definition.languages == {"subject": ["python"]}
    assert definition.documentation.evidence.startswith("The finding")
    assert definition.documentation.exceptions.startswith("Keep imports")
    assert definition.fixes[0].name == "query"


def test_catalog_rejects_a_missing_required_docstring_section() -> None:
    def incomplete_function(subject: Table[ImportBindingFact]) -> OccurrenceQuery:
        """Report an import without explaining the rule."""
        raise AssertionError(f"the invalid documentation fixture cannot run against {subject}")

    incomplete_function.__module__ = "mcmr.rules.python.deterministic.imports.style.r0004"
    incomplete = rule("PY-IMPO0004")(incomplete_function)
    with pytest.raises(ValueError, match="Definition"):
        _ = incomplete.instructions
    with pytest.raises(ValueError, match="Definition"):
        _ = Catalog(modules=[module_with(incomplete.module, incomplete=incomplete)]).definitions


def test_catalog_rejects_duplicate_ids() -> None:
    first = rule(unused_import.id)(unused_import.function)
    second = rule(unused_import.id)(unused_import.function)
    with pytest.raises(ValueError, match="Duplicate rule ID PY-IMPO0003"):
        _ = Catalog(
            modules=[
                module_with(first.module, first=first),
                module_with(second.module, second=second),
            ]
        ).definitions


def test_catalog_rejects_policy_shapes_and_incomplete_category_outcomes() -> None:
    wrong_shape = unused_import.model_copy(update={"policy": Category(good={"unused"})})
    incomplete = module_cohesion.model_copy(update={"policy": Category(good={"cohesive"})})

    with pytest.raises(TypeError, match="does not match its bool output"):
        Catalog(modules=[]).definition(wrong_shape)
    with pytest.raises(ValueError, match="classify every output category"):
        Catalog(modules=[]).definition(incomplete)


def test_rule_annotations_remain_available_to_runtime_discovery() -> None:
    hints = get_type_hints(unused_import.function, include_extras=True)

    assert hints["subject"] == Table[ImportBindingFact]
    assert hints["return"] == OccurrenceQuery


def test_catalog_rejects_a_rule_without_a_table_input() -> None:
    @rule("PY-IMPO0005")
    def no_input() -> bool:
        """Provide no injectable fact.

        Definition
        ----------
        This invalid example has no fact input.

        Examples
        --------
        A rule without a subject fails.

        References
        ----------
        MCMR rule contract
        """
        return False

    no_input.function.__module__ = "mcmr.rules.python.deterministic.imports.hygiene.r0005"
    no_input = rule(no_input.id)(no_input.function)
    with pytest.raises(TypeError, match="needs at least one Table input"):
        _ = Catalog(modules=[module_with(no_input.module, no_input=no_input)]).definitions


def test_catalog_requires_the_table_rule_contract() -> None:
    def row_rule(subject: ImportBindingFact) -> bool:
        return subject.has_qualifying_use

    row_rule.__module__ = "mcmr.rules.python.deterministic.imports.hygiene.r0005"
    row_rule.__doc__ = unused_import.raw_documentation
    invalid = rule("PY-IMPO0005")(row_rule)

    with pytest.raises(TypeError, match="must receive at least one typed Table"):
        _ = Catalog(modules=[module_with(invalid.module, invalid=invalid)]).definitions


def test_catalog_requires_every_injected_input_annotation() -> None:
    def missing_annotation(subject: Table[ImportBindingFact], backend) -> OccurrenceQuery:
        raise AssertionError(f"invalid fixture cannot run against {subject} and {backend}")

    missing_annotation.__module__ = "mcmr.rules.python.deterministic.imports.hygiene.r0005"
    missing_annotation.__doc__ = unused_import.raw_documentation
    invalid = rule("PY-IMPO0005")(missing_annotation)

    with pytest.raises(TypeError, match="input backend needs an annotation"):
        _ = Catalog(modules=[module_with(invalid.module, invalid=invalid)]).definitions


def test_catalog_requires_one_relational_query_result() -> None:
    @rule("PY-IMPO0005")
    def primitive_rule(subject: Table[ImportBindingFact]) -> bool:
        return bool(subject)

    primitive_rule.function.__module__ = "mcmr.rules.python.deterministic.imports.hygiene.r0005"
    primitive_rule.function.__doc__ = unused_import.raw_documentation
    invalid = rule(primitive_rule.id)(primitive_rule.function)

    with pytest.raises(TypeError, match="must return one RuleQuery or ModelQuery"):
        _ = Catalog(modules=[module_with(invalid.module, invalid=invalid)]).definitions


def test_catalog_rejects_a_noncanonical_module_path() -> None:
    function = unused_import.function
    original = function.__module__
    function.__module__ = "mcmr.custom.unstable"
    invalid = rule(unused_import.id)(function)
    function.__module__ = original
    with pytest.raises(ValueError, match="does not follow"):
        _ = Catalog(modules=[module_with(invalid.module, invalid=invalid)]).definitions


def test_installed_plugins_use_the_same_rule_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An installed module joins discovery and keeps structural identity validation."""
    plugin = module_with(
        "acme.rules.python.deterministic.imports.r0001",
        unused_import=unused_import.model_copy(
            update={
                "id": "PY-IMPO0001",
                "module": "acme.rules.python.deterministic.imports.r0001",
            }
        ),
    )
    entry = EntryPoint(name="acme", value=plugin.__name__, group="mcmr.rules")
    monkeypatch.setitem(sys.modules, plugin.__name__, plugin)
    monkeypatch.setattr(
        "mcmr.rulebook.discovery.metadata.entry_points",
        lambda **selection: (entry,) if selection == {"group": "mcmr.rules"} else (),
    )

    discovered = RuleModuleDiscovery(package="mcmr.rules.python.deterministic.imports").modules
    definition = Catalog(modules=[plugin]).definitions[0]

    assert plugin in discovered
    assert definition.id == "PY-IMPO0001"


def test_plugin_discovery_can_be_disabled_and_rejects_nonmodules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    package = "mcmr.rules.python.deterministic.imports"
    builtins = RuleModuleDiscovery(package=package, include_plugins=False).modules
    entry = EntryPoint(name="invalid", value="builtins:len", group="mcmr.rules")
    monkeypatch.setattr(
        "mcmr.rulebook.discovery.metadata.entry_points",
        lambda **selection: (entry,) if selection == {"group": "mcmr.rules"} else (),
    )

    assert builtins
    with pytest.raises(TypeError, match="must load a module or package"):
        _ = RuleModuleDiscovery(package=package).modules


def test_rule_instructions_are_the_documented_definition() -> None:
    assert unused_import.instructions.startswith("Report one resolved import binding")


@pytest.mark.parametrize(
    ("candidate", "message"),
    [
        (lambda subject, *extra: False, "cannot use variadic input extra"),
        (lambda subject, maximum=1: False, "setting maximum must be keyword-only"),
    ],
)
def test_catalog_rejects_ambiguous_rule_parameters(candidate: FunctionType, message: str) -> None:
    candidate.__module__ = "mcmr.rules.python.deterministic.imports.hygiene.r0005"
    candidate.__annotations__ = {"subject": Table[ImportBindingFact], "return": bool}
    candidate.__doc__ = unused_import.raw_documentation
    invalid = rule("PY-IMPO0005")(candidate)
    with pytest.raises(TypeError, match=message):
        _ = Catalog(modules=[module_with(invalid.module, invalid=invalid)]).definitions


def test_catalog_rejects_an_unbounded_numeric_setting() -> None:
    @rule("PY-IMPO0005")
    def unbounded(subject: Table[ImportBindingFact], *, minimum: int = 1) -> bool:
        return False

    unbounded.function.__module__ = "mcmr.rules.python.deterministic.imports.hygiene.r0005"
    unbounded.function.__doc__ = unused_import.raw_documentation
    invalid = rule(unbounded.id)(unbounded.function)

    with pytest.raises(TypeError, match="minimum needs a constrained annotation"):
        _ = Catalog(modules=[module_with(invalid.module, invalid=invalid)]).definitions


def test_a_lane_owns_the_leading_digit_of_its_rule_numbers() -> None:
    assert (
        Catalog.identity("mcmr.rules.general.deterministic.errors.handling.r0001", "ALL-ERRO0001")[
            1
        ].value
        == "deterministic"
    )
    assert (
        Catalog.identity("mcmr.rules.general.contextual.errors.r1001", "ALL-ERRO1001")[1].value
        == "contextual"
    )
    assert (
        Catalog.identity("mcmr.rules.general.contextual.comments.r1001", "ALL-COMM1001")[1].value
        == "contextual"
    )

    with pytest.raises(ValueError, match="belongs to another lane"):
        Catalog.identity("mcmr.rules.general.contextual.errors.r0001", "ALL-ERRO0001")


def test_rule_identity_keeps_the_family_across_semantic_subpackages() -> None:
    scope, lane, family, slot = Catalog.identity(
        "mcmr.rules.python.deterministic.testing.execution.asyncio",
        "PY-TEST0017",
    )
    assert (scope.value, lane.value, family, slot) == (
        "python",
        "deterministic",
        "testing",
        "0017",
    )


def test_rule_identity_rejects_a_scope_or_family_mismatch() -> None:
    with pytest.raises(ValueError, match="does not match"):
        Catalog.identity("mcmr.rules.python.deterministic.imports.unused", "PY-TEST0001")


def test_rule_identity_rejects_an_invalid_public_shape() -> None:
    with pytest.raises(ValidationError, match="string_pattern_mismatch"):
        rule("python-imports-1")(unused_import.function)


def test_catalog_rejects_a_gap_in_one_family() -> None:
    first = rule("PY-IMPO0001")(unused_import.function)
    third = rule("PY-IMPO0003")(unused_import.function)

    with pytest.raises(ValueError, match="available ID is PY-IMPO0002"):
        _ = Catalog(
            modules=[
                module_with(first.module, first=first),
                module_with(third.module, third=third),
            ]
        ).definitions


def test_catalog_rejects_an_active_rule_using_a_retired_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(Catalog.retirements, unused_import.id, "retired for the test")

    with pytest.raises(ValueError, match="repeat retired IDs"):
        Catalog.validate_numbering([Catalog(modules=[]).definition(unused_import)])


def test_catalog_rejects_a_retirement_without_a_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(Catalog.retirements, "ALL-DATA0005", "")

    with pytest.raises(ValueError, match="needs a reason"):
        Catalog.validate_numbering([])


@pytest.mark.parametrize(
    ("module", "identifier", "language", "message"),
    [
        (
            "mcmr.rules.general.deterministic.imports.example",
            "ALL-IMPO0001",
            RuleScope.GENERAL,
            "cannot name general as a language",
        ),
        (
            "mcmr.rules.python.deterministic.imports.example",
            "PY-IMPO0001",
            RuleScope.RUST,
            "must use its python scope",
        ),
    ],
)
def test_catalog_rejects_conflicting_table_language_metadata(
    *,
    module: str,
    identifier: str,
    language: RuleScope,
    message: str,
) -> None:
    def conflicting(
        subject: Annotated[Table[ImportBindingFact], language],
    ) -> OccurrenceQuery:
        raise AssertionError(f"the invalid language fixture cannot run against {subject}")

    conflicting.__module__ = module
    conflicting.__doc__ = unused_import.raw_documentation
    invalid = rule(identifier)(conflicting)

    with pytest.raises(TypeError, match=message):
        Catalog(modules=[]).definition(invalid)


def test_only_the_primary_table_inherits_the_rule_language_scope() -> None:
    assert Catalog.languages(
        "PY-IMPO0001",
        RuleScope.PYTHON,
        {"subject": set(), "configuration": set()},
    ) == {"subject": {"python"}, "configuration": set()}


def test_every_rule_number_matches_its_lane_and_every_rule_is_table_native() -> None:
    catalog = Catalog(modules=RuleModuleDiscovery().modules)
    wrong = [
        definition.id
        for definition in catalog.definitions
        if not definition.id.rsplit("-", 1)[-1][4:].startswith(RuleLane(definition.lane).slot)
    ]

    assert not wrong
    assert len(catalog.rules) == 275
    assert all(rule.table_native for rule in catalog.rules)
    assert all(rule.query_native for rule in catalog.rules)
