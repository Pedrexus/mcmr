import inspect
import tomllib
from typing import TYPE_CHECKING, Self

from patos import FrozenModel
from pydantic import JsonValue

from ...domain.policy import RulePolicies
from .contextual import ContextualConfiguration
from .execution import ExecutionConfiguration, ExecutionOverride
from .rules import RuleConfiguration, validated_setting
from .scan import ScanConfiguration
from .selection import is_match

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from ...domain.contracts import RuleContract, RuleSetting
    from ...rulebook.catalog import RuleDefinition


class MCMRConfiguration(FrozenModel):
    """Read and validate the project policy under `tool.mcmr`."""

    select: list[str] = ["*"]
    ignore: list[str] = []
    rules: dict[str, RuleConfiguration] = {}
    scan: ScanConfiguration = ScanConfiguration()
    execution: ExecutionConfiguration = ExecutionConfiguration()
    contextual: ContextualConfiguration = ContextualConfiguration()
    providers: dict[str, dict[str, JsonValue]] = {}

    @classmethod
    def read(cls, root: Path) -> Self:
        """Read one repository's MCMR table, or return defaults when it has none."""
        path = root / "pyproject.toml"
        try:
            content = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return cls()
        return cls.model_validate(tomllib.loads(content).get("tool", {}).get("mcmr", {}))

    def exclusions(self, definitions: Sequence[RuleDefinition]) -> dict[str, list[str]]:
        """Return per-rule source globs keyed by the runtime callable path."""
        by_id = {definition.id: definition for definition in definitions}
        return {
            by_id[rule_id].callable: list(configured.exclude)
            for rule_id, configured in self.rules.items()
            if configured.exclude
        }

    def matched(
        self,
        definitions: Sequence[RuleDefinition],
        override: str = "",
    ) -> list[RuleDefinition]:
        """Return the complete requested scope, including rules configured as disabled."""
        self._validate_policies(definitions)
        patterns = [override] if override else self.select
        matched = [
            definition for definition in definitions if self._selected(definition, patterns)
        ]
        if patterns and not matched:
            raise ValueError("No rules match the selection and enabled execution modes")
        return matched

    def policies(self) -> RulePolicies:
        """Return rule-owned policies with exact project overrides."""
        stated = {
            rule_id: configured.policy
            for rule_id, configured in self.rules.items()
            if configured.policy is not None
        }
        return RulePolicies(overrides=stated)

    def selected(
        self,
        definitions: Sequence[RuleDefinition],
        *,
        rules: Sequence[RuleContract],
        override: str = "",
    ) -> list[RuleContract]:
        """Return enabled rules selected by ID or callable pattern."""
        matched = {definition.callable for definition in self.matched(definitions, override)}
        by_callable = {definition.callable: definition for definition in definitions}
        return [
            rule
            for rule in rules
            if rule.callable_path in matched
            and self.rules.get(by_callable[rule.callable_path].id, RuleConfiguration()).enabled
        ]

    def settings(
        self,
        definitions: Sequence[RuleDefinition],
        *,
        rules: Sequence[RuleContract],
    ) -> dict[str, dict[str, RuleSetting]]:
        """Validate and coerce configured values against each rule's annotations."""
        by_id = {definition.id: definition for definition in definitions}
        runtime = {rule.callable_path: rule for rule in rules}
        configured: dict[str, dict[str, RuleSetting]] = {}
        for rule_id, values in self.rules.items():
            if rule_id not in by_id:
                raise ValueError(f"Unknown configured rule {rule_id}")
            rule = runtime[by_id[rule_id].callable]
            configured[rule.callable_path] = self._rule_settings(rule_id, values, rule)
        return configured

    def with_execution(
        self,
        *,
        deterministic: ExecutionOverride = ExecutionOverride.UNCHANGED,
        contextual: ExecutionOverride = ExecutionOverride.UNCHANGED,
        external: ExecutionOverride = ExecutionOverride.UNCHANGED,
    ) -> Self:
        """Apply only execution choices explicitly supplied by the command line."""
        stated = {
            name: choice is ExecutionOverride.ENABLED
            for name, choice in [
                ("deterministic", deterministic),
                ("contextual", contextual),
                ("external", external),
            ]
            if choice is not ExecutionOverride.UNCHANGED
        }
        return self.model_copy(update={"execution": self.execution.model_copy(update=stated)})

    @staticmethod
    def _rule_settings(
        rule_id: str,
        values: RuleConfiguration,
        rule: RuleContract,
    ) -> dict[str, RuleSetting]:
        """Validate settings for one resolved runtime rule."""
        allowed = {
            parameter.name
            for parameter in rule.signature.parameters.values()
            if parameter.default is not inspect.Parameter.empty
        }
        if unknown := sorted(set(values.settings) - allowed):
            raise ValueError(f"Unknown setting for {rule_id} {', '.join(unknown)}")
        return {
            name: validated_setting(rule.hints[name], value)
            for name, value in values.settings.items()
        }

    def _selected(self, definition: RuleDefinition, patterns: Sequence[str]) -> bool:
        """Return whether one definition matches selection, ignores, and execution mode."""
        selected = any(
            is_match(rule_id=definition.id, callable_path=definition.callable, pattern=pattern)
            for pattern in patterns
        )
        ignored = any(
            is_match(rule_id=definition.id, callable_path=definition.callable, pattern=pattern)
            for pattern in self.ignore
        )
        return (
            selected
            and not ignored
            and self.execution.includes(
                external=definition.external,
                lane=definition.lane,
            )
        )

    def _validate_policies(self, definitions: Sequence[RuleDefinition]) -> None:
        """Reject unknown rules and policies incompatible with their output contracts."""
        available = {definition.id for definition in definitions}
        if unknown := sorted(set(self.rules) - available):
            raise ValueError(f"Unknown configured rule {', '.join(unknown)}")
        for definition in definitions:
            configured = self.rules.get(definition.id)
            if configured is not None and configured.policy is not None:
                definition.validate_policy(configured.policy, "configured policy")
