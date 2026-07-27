from types import FunctionType, ModuleType
from typing import get_type_hints

import pytest

from mcmr import rule
from mcmr.catalog import Catalog
from mcmr.discovery import RuleModuleDiscovery
from mcmr.facts import ImportBindingFact
from mcmr.models import (
    FixContract,
    FixPlan,
    Occurrence,
    RuleContract,
    RuleLane,
    SourceRewrite,
)


def module_with(name: str, **members: RuleContract | FixContract) -> ModuleType:
    """Create one synthetic rule module for catalog tests."""
    module = ModuleType(name)
    module.__dict__.update(members)
    return module


@rule
def documented_rule(subject: ImportBindingFact) -> Occurrence:
    """Report an unused import.

    Definition
    ----------
    Report one resolved import binding without a qualifying use.

    Evidence
    --------
    Retain the binding span and reference summary.

    Exceptions
    ----------
    Explicit re-exports and documented side-effect imports are retained.

    Examples
    --------
    `import json` with no reference fails.

    References
    ----------
    Ruff F401
    """
    return not subject.has_qualifying_use


documented_rule.function.__module__ = "mcmr.rules.python.deterministic.imports.r0003"
documented_rule = rule(documented_rule.function)


def test_catalog_derives_identity_and_complete_documentation() -> None:
    candidate = documented_rule
    catalog = Catalog(modules=[module_with(candidate.module, unused_import=candidate)])
    definition = catalog.definitions[0]
    assert definition.id == "PY-IMPO0003"
    assert definition.lane == "deterministic"
    assert definition.fact == "ImportBindingFact"
    assert definition.documentation.evidence.startswith("Retain")
    assert definition.documentation.exceptions.startswith("Explicit")


def test_catalog_rejects_a_missing_required_docstring_section() -> None:
    def incomplete_function(subject: ImportBindingFact) -> Occurrence:
        """Report an import without explaining the rule."""
        return not subject.has_qualifying_use

    incomplete_function.__module__ = "mcmr.rules.python.deterministic.imports.r0004"
    incomplete = rule(incomplete_function)
    with pytest.raises(ValueError, match="Definition"):
        _ = Catalog(modules=[module_with(incomplete.module, incomplete=incomplete)]).definitions


def test_catalog_rejects_duplicate_ids() -> None:
    first = rule(documented_rule.function)
    second = rule(documented_rule.function)
    with pytest.raises(ValueError, match="Duplicate rule ID PY-IMPO0003"):
        _ = Catalog(
            modules=[
                module_with(first.module, first=first),
                module_with(second.module, second=second),
            ]
        ).definitions


def test_catalog_rejects_multiple_default_fixes() -> None:
    candidate = documented_rule

    @candidate.fix(is_default=True)
    def remove(subject: ImportBindingFact) -> list[SourceRewrite]:
        return []

    @candidate.fix(is_default=True)
    def reexport(subject: ImportBindingFact) -> list[SourceRewrite]:
        return []

    with pytest.raises(ValueError, match="multiple default fixes"):
        _ = Catalog(
            modules=[
                module_with(
                    candidate.module,
                    candidate=candidate,
                    remove=remove,
                    reexport=reexport,
                )
            ]
        ).definitions


def test_rule_annotations_remain_available_to_runtime_discovery() -> None:
    hints = get_type_hints(documented_rule.function, include_extras=True)
    assert hints["subject"] is ImportBindingFact
    assert hints["return"] is Occurrence
    assert FixPlan.model_fields


def test_catalog_rejects_a_rule_without_a_fact_input() -> None:
    @rule
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

    no_input.function.__module__ = "mcmr.rules.python.deterministic.imports.r0005"
    no_input = rule(no_input.function)
    with pytest.raises(TypeError, match="needs one Fact input"):
        _ = Catalog(modules=[module_with(no_input.module, no_input=no_input)]).definitions


def test_catalog_rejects_a_noncanonical_module_path() -> None:
    candidate = documented_rule
    candidate.function.__module__ = "mcmr.custom.unstable"
    invalid = rule(candidate.function)
    candidate.function.__module__ = "mcmr.rules.python.deterministic.imports.r0003"
    with pytest.raises(ValueError, match="does not follow"):
        _ = Catalog(modules=[module_with(invalid.module, invalid=invalid)]).definitions


@pytest.mark.parametrize(
    ("candidate", "message"),
    [
        (
            lambda subject, *extra: False,
            "cannot use variadic input extra",
        ),
        (
            lambda subject, maximum=1: False,
            "setting maximum must be keyword-only",
        ),
    ],
)
def test_catalog_rejects_ambiguous_rule_parameters(candidate: FunctionType, message: str) -> None:
    candidate.__module__ = "mcmr.rules.python.deterministic.imports.r0005"
    candidate.__annotations__ = {"subject": ImportBindingFact, "return": bool}
    candidate.__doc__ = documented_rule.raw_documentation
    invalid = rule(candidate)
    with pytest.raises(TypeError, match=message):
        _ = Catalog(modules=[module_with(invalid.module, invalid=invalid)]).definitions


def test_catalog_rejects_a_fix_with_different_inputs() -> None:
    candidate = documented_rule

    @candidate.fix()
    def incompatible(subject: ImportBindingFact, *, mode: str = "remove") -> list[SourceRewrite]:
        return []

    with pytest.raises(TypeError, match="inputs must match"):
        _ = Catalog(
            modules=[module_with(candidate.module, candidate=candidate, incompatible=incompatible)]
        ).definitions


def test_catalog_infers_a_single_fix_as_default() -> None:
    candidate = documented_rule

    @candidate.fix()
    def remove(subject: ImportBindingFact) -> list[SourceRewrite]:
        return []

    definition = Catalog(
        modules=[module_with(candidate.module, candidate=candidate, remove=remove)]
    ).definitions[0]
    assert definition.fixes[0].is_default


def test_a_lane_owns_the_leading_digit_of_its_rule_numbers() -> None:
    """Two lanes in one family used to mint the same identifier, so the digit is now checked.

    `general/llm/errors/r0001` and `general/deterministic/errors/r0001` both derived
    `ALL-ERRO0001` and the catalog refused to build. Reserving the digit per lane makes that
    impossible rather than caught, and a file numbered against its own lane is rejected here.
    """
    assert Catalog.identity("mcmr.rules.general.deterministic.errors.r0001")[1] is (
        RuleLane.DETERMINISTIC
    )
    assert Catalog.identity("mcmr.rules.general.llm.errors.r2001")[1] is RuleLane.LLM
    assert Catalog.identity("mcmr.rules.general.gliner.comments.r1003")[1] is RuleLane.GLINER

    with pytest.raises(ValueError, match="belongs to another lane"):
        Catalog.identity("mcmr.rules.general.llm.errors.r0001")


def test_every_rule_number_matches_the_lane_that_holds_it() -> None:
    """The whole catalog obeys the scheme, not only the cases a unit test names."""
    catalog = Catalog(modules=RuleModuleDiscovery().modules)
    wrong = [
        definition.id
        for definition in catalog.definitions
        if not definition.id.rsplit("-", 1)[-1][4:].startswith(RuleLane(definition.lane).slot)
    ]

    assert not wrong, sorted(wrong)
