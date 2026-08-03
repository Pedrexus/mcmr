from importlib.resources import files
from typing import TYPE_CHECKING

from patos import FrozenModel

from ..capabilities import CapabilityInventory, CapabilityMigration, ReplacementState
from ..rules import LegacyRuleInventory, RuleMigration
from .audit import ReplacementAudit

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable, Sequence

    from ....domain.contracts import RuleDefinition


class Ge4mReplacement(FrozenModel):
    """Audit the frozen GE4M surface against MCMR without executing the old tool."""

    inventory: LegacyRuleInventory
    rules: RuleMigration
    capabilities: CapabilityInventory
    capability_migration: CapabilityMigration

    @staticmethod
    def difference(label: str, values: Collection[str]) -> list[str]:
        """Render one stable issue per unexpected ledger value."""
        return [f"{label} {value}" for value in sorted(values)]

    @staticmethod
    def duplicates(values: Iterable[str]) -> set[str]:
        """Return values repeated in one independently maintained ledger side."""
        seen: set[str] = set()
        repeated: set[str] = set()
        for value in values:
            if value in seen:
                repeated.add(value)
            seen.add(value)
        return repeated

    @staticmethod
    def load_asset[Asset: FrozenModel](model: type[Asset], asset: str) -> Asset:
        """Validate one packaged JSON asset as its concrete ledger model."""
        source = files("mcmr.data").joinpath(asset).read_text()
        return model.model_validate_json(source)

    @classmethod
    def load(cls) -> Ge4mReplacement:
        """Load all four independent halves of the replacement ledger."""
        return cls(
            inventory=cls.load_asset(LegacyRuleInventory, "ge4m-rules.json"),
            rules=cls.load_asset(RuleMigration, "ge4m-migration.json"),
            capabilities=cls.load_asset(CapabilityInventory, "ge4m-capabilities.json"),
            capability_migration=cls.load_asset(
                CapabilityMigration, "ge4m-capability-migration.json"
            ),
        )

    def audit(self, definitions: Sequence[RuleDefinition]) -> ReplacementAudit:
        """Compare both ledgers in both directions and validate every live MCMR target."""
        legacy_rules = {item.id for item in self.inventory.rules}
        mapped_rules = {item.source_id for item in self.rules.rules}
        legacy_capabilities = {item.id for item in self.capabilities.capabilities}
        mapped_capabilities = {item.source_id for item in self.capability_migration.capabilities}
        missing = self.missing_capability_count()
        issues = [*self.rule_issues(definitions), *self.capability_issues()]
        return ReplacementAudit(
            legacy_rules=len(legacy_rules),
            mapped_rules=len(mapped_rules),
            legacy_capabilities=len(legacy_capabilities),
            mapped_capabilities=len(mapped_capabilities),
            missing_capabilities=missing,
            issues=issues,
        )

    def capability_issues(self) -> list[str]:
        """Return every mismatch between the capability inventory and migration."""
        legacy = {item.id for item in self.capabilities.capabilities}
        mapped = {item.source_id for item in self.capability_migration.capabilities}
        return [
            *self.difference("unmapped GE4M capability", legacy - mapped),
            *self.difference("unknown mapped GE4M capability", mapped - legacy),
            *self.difference(
                "duplicate mapped GE4M capability",
                self.duplicates(item.source_id for item in self.capability_migration.capabilities),
            ),
        ]

    def missing_capability_count(self) -> int:
        """Return how many legacy capabilities still have no final disposition."""
        return sum(
            item.state is ReplacementState.MISSING
            for item in self.capability_migration.capabilities
        )

    def rule_issues(self, definitions: Sequence[RuleDefinition]) -> list[str]:
        """Return every mismatch between the rule inventory, migration, and catalog."""
        legacy = {item.id for item in self.inventory.rules}
        mapped = {item.source_id for item in self.rules.rules}
        targets = {item.id for item in definitions}
        referenced = {target for item in self.rules.rules for target in item.target_ids}
        return [
            *self.difference("unmapped GE4M rule", legacy - mapped),
            *self.difference("unknown mapped GE4M rule", mapped - legacy),
            *self.difference("unknown MCMR target rule", referenced - targets),
            *self.difference(
                "duplicate mapped GE4M rule",
                self.duplicates(item.source_id for item in self.rules.rules),
            ),
        ]
