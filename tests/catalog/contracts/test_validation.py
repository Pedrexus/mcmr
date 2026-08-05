from typing import TYPE_CHECKING, Annotated

import pytest
from pydantic import ValidationError

from mcmr import rule
from mcmr.domain.contracts import RuleLane, RuleScope
from mcmr.facts import ImportBindingFact
from mcmr.plugins import Table
from mcmr.query import OccurrenceQuery
from mcmr.rulebook.catalog import Catalog
from mcmr.rulebook.discovery import RuleModuleDiscovery
from mcmr.rules.python import unused_import

from .support import module_with

if TYPE_CHECKING:
    from types import FunctionType


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
    ) -> bool:
        raise AssertionError(f"the invalid language fixture cannot run against {subject}")

    conflicting.__module__ = module
    conflicting.__doc__ = unused_import.raw_documentation
    conflicting.__annotations__["return"] = OccurrenceQuery
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
    assert len(catalog.rules) == 284
    assert all(rule.table_native for rule in catalog.rules)
    assert all(rule.query_native for rule in catalog.rules)
