import sys
from importlib.metadata import EntryPoint
from typing import get_type_hints

import pytest

from mcmr import Category, rule
from mcmr.facts import ImportBindingFact
from mcmr.plugins import Table
from mcmr.query import OccurrenceQuery
from mcmr.rulebook.catalog import Catalog
from mcmr.rulebook.discovery import RuleModuleDiscovery
from mcmr.rules.general import module_cohesion
from mcmr.rules.python import unused_import

from .support import module_with


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
