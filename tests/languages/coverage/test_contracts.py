import pytest

from mcmr.accounting.upstream import ClaimIndex, ToolRegistry
from mcmr.domain.contracts import RuleLane, RuleScope
from mcmr.facts import buildable
from mcmr.rulebook.catalog import Catalog
from mcmr.rulebook.discovery import RuleModuleDiscovery

from .support import gap_reasons, general_families, language_fixtures, provider_gap_reasons


def test_the_native_registry_cannot_name_a_declaration_that_is_not_loaded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stale registry name fails rather than silently making its rules unavailable."""
    monkeypatch.setitem(
        buildable.__globals__,
        "_native_names",
        set(buildable()) | {"MissingFact"},
    )

    with pytest.raises(RuntimeError, match="native fact declarations are missing MissingFact"):
        buildable()


def test_every_declared_gap_names_a_family_a_general_rule_reads() -> None:
    """The ledger cannot outlive the gap it records, and cannot invent one either."""
    families = general_families()

    assert set(gap_reasons()) <= families
    assert all(
        set(languages) <= set(language_fixtures()) - {"python"}
        for languages in gap_reasons().values()
    )
    assert all(reason for languages in gap_reasons().values() for reason in languages.values())


def test_every_unbuilt_local_deterministic_family_has_an_evidence_contract() -> None:
    """An unavailable rule stays unavailable until a provider can prove its full intent.

    Rules backed by explicitly external facts have their own adapter boundary. Every other
    deterministic family is expected from repository evidence, so it must either be buildable or
    remain in the provider-gap ledger with the evidence that a real implementation still owes.
    """
    definitions = Catalog(modules=RuleModuleDiscovery().modules).definitions
    missing = {
        definition.fact
        for definition in definitions
        if definition.lane == RuleLane.DETERMINISTIC
        and not definition.external
        and definition.fact not in buildable()
    }

    assert missing == set(provider_gap_reasons())
    assert all(requirement.strip() for requirement in provider_gap_reasons().values())


def test_every_general_tool_claim_has_a_provider_in_the_tools_languages() -> None:
    """A general rule cannot cover a tool where its fact family is absent.

    Tool profiles state the languages their inventories describe, and the frontend ledger states
    every family those languages still lack. Joining the two makes language support part of the
    coverage account instead of an assumption hidden behind an `ALL` identifier.
    """
    definitions = list(Catalog(modules=RuleModuleDiscovery().modules).definitions)
    profiles = ToolRegistry().by_name
    claims = ClaimIndex(definitions=definitions).claims
    wrong = {
        (claim.rule, upstream.tool, language.value, claim.fact)
        for claim in claims
        if (upstream := claim.upstream) is not None
        if claim.scope is RuleScope.GENERAL
        for language in profiles[upstream.tool.casefold()].languages
        if language.value in gap_reasons().get(claim.fact, {})
    }

    assert not wrong, sorted(wrong)
