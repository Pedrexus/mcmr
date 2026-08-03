import pytest
from pydantic import ValidationError

from mcmr.accounting.replacement import (
    CapabilityInventory,
    CapabilityMigration,
    CapabilityReplacement,
    Ge4mReplacement,
    LegacyCapability,
    LegacyRule,
    LegacyRuleInventory,
    ReplacementAudit,
    ReplacementState,
    RuleMigration,
    RuleReplacement,
)
from mcmr.rulebook.catalog import Catalog
from mcmr.rulebook.discovery import RuleModuleDiscovery


def test_the_frozen_ge4m_ledgers_retain_their_typed_contracts() -> None:
    """The replacement ledger retains its typed rule and capability contracts."""
    replacement = Ge4mReplacement.load()

    assert isinstance(replacement.inventory, LegacyRuleInventory)
    assert isinstance(replacement.inventory.rules[0], LegacyRule)
    assert isinstance(replacement.rules, RuleMigration)
    assert isinstance(replacement.rules.rules[0], RuleReplacement)
    assert isinstance(replacement.capabilities, CapabilityInventory)
    assert isinstance(replacement.capabilities.capabilities[0], LegacyCapability)
    assert isinstance(replacement.capability_migration, CapabilityMigration)
    assert isinstance(replacement.capability_migration.capabilities[0], CapabilityReplacement)


def test_the_frozen_ge4m_ledgers_cover_rules_and_capabilities_in_both_directions() -> None:
    """Deleting or inventing an old entry remains visible against the live catalog."""
    replacement = Ge4mReplacement.load()
    catalog = Catalog(modules=RuleModuleDiscovery().modules)
    audit = replacement.audit(list(catalog.definitions))

    assert isinstance(audit, ReplacementAudit)
    assert (
        audit.legacy_rules,
        audit.mapped_rules,
        audit.legacy_capabilities,
        audit.mapped_capabilities,
        audit.issues,
        audit.missing_capabilities,
        audit.complete,
    ) == (205, 205, 18, 18, [], 0, True)


def test_every_legacy_rule_has_a_successor_or_an_explicit_retirement() -> None:
    replacement = Ge4mReplacement.load()
    target_ids = {
        definition.id for definition in Catalog(modules=RuleModuleDiscovery().modules).definitions
    }

    assert all(
        (mapping.relation == "retired" and not mapping.target_ids)
        or (mapping.relation != "retired" and set(mapping.target_ids) <= target_ids)
        for mapping in replacement.rules.rules
    )
    assert all(
        mapping.state
        in {
            ReplacementState.NATIVE,
            ReplacementState.DELEGATED,
            ReplacementState.RETIRED,
            ReplacementState.MISSING,
        }
        for mapping in replacement.capability_migration.capabilities
    )
    assert Ge4mReplacement.duplicates(("same", "same")) == {"same"}


@pytest.mark.parametrize(
    ("target_ids", "relation", "message"),
    [
        ([], "same_id", "at least one target"),
        (["ALL-TEST1001"], "retired", "no targets"),
    ],
)
def test_rule_replacement_requires_an_honest_retirement_shape(
    *, target_ids: list[str], relation: str, message: str
) -> None:
    with pytest.raises(ValidationError, match=message):
        RuleReplacement(source_id="PY-TEST0006", target_ids=target_ids, relation=relation)
