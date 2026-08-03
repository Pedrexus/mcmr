from collections.abc import Mapping, Sequence
from functools import cached_property
from typing import TYPE_CHECKING

from patos import FrozenModel, Runtime

from ...domain.contracts import (
    RuleContract,
    RuleDependency,
    RuleSetting,
    output_contract,
)
from .batch import RuleBatch
from .prepared import PreparedRule

if TYPE_CHECKING:
    from ...facts.foundation import Fact


class RuleEngine(FrozenModel):
    """Compile selected table rules and their invariant inputs once."""

    rules: list[Runtime[RuleContract]]
    settings: Mapping[str, Mapping[str, RuleSetting]] = {}
    exclusions: Mapping[str, Sequence[str]] = {}
    dependencies: Runtime[Mapping[type, RuleDependency]] = {}

    @cached_property
    def batches(self) -> list[RuleBatch]:
        """Partition rules into independent lazy graphs without duplicating any table."""
        batches: list[RuleBatch] = []
        for rule in self.prepared:
            connected = [batch for batch in batches if batch.connected(rule)]
            if not connected:
                batches.append(RuleBatch(rules=[rule]))
                continue
            first = min(batches.index(batch) for batch in connected)
            merged = RuleBatch(
                rules=[item for batch in connected for item in batch.rules] + [rule]
            )
            batches = [batch for batch in batches if batch not in connected]
            batches.insert(first, merged)
        return batches

    @cached_property
    def families(self) -> set[type[Fact]]:
        """Return the union of every table family selected rules require."""
        return {family for rule in self.rules for _, family in rule.tables}

    @cached_property
    def fix_counts(self) -> dict[str, int]:
        """Return whether each rule query can propose its declared repair."""
        return {rule.callable_path: int(rule.query_fix_safety is not None) for rule in self.rules}

    @cached_property
    def prepared(self) -> list[PreparedRule]:
        """Compile invariant settings and eligibility without assigning family ownership."""
        return [
            PreparedRule.of(
                rule,
                output_contract(rule.hints["return"]),
                self.settings.get(rule.callable_path, {}),
                self.exclusions.get(rule.callable_path, []),
            )
            for rule in self.rules
            if all(hint in self.dependencies for _, hint in rule.injected)
        ]
