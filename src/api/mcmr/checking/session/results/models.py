from typing import TYPE_CHECKING

from patos import FrozenModel
from pydantic import NonNegativeInt

from ....domain.contracts import EngineStats, Observation, RuleDefinition
from ....domain.policy import RulePolicies, Verdict
from ....kernel import KernelStats

if TYPE_CHECKING:
    from collections.abc import Sequence


class _JudgmentModels:
    """Own the immutable result models produced by one completed judgment."""

    class Assessment(FrozenModel):
        """Retain one rule observation and its verdict."""

        definition: RuleDefinition
        observation: Observation
        verdict: Verdict

    class RuleJudgment(FrozenModel):
        """Retain one rule's totals and bounded failed observations."""

        definition: RuleDefinition
        observations: NonNegativeInt = 0
        unassessed: NonNegativeInt = 0
        failure_count: NonNegativeInt = 0
        finding_count: NonNegativeInt = 0
        failures: list[Observation] = []

    class Verdicts(FrozenModel):
        """Retain everything one engine pass concluded before presentation."""

        policies: RulePolicies
        rules: list[RuleJudgment] = []
        failure_limit: NonNegativeInt | None = None
        kernel: KernelStats = KernelStats()
        engine: EngineStats

        @property
        def failure_count(self) -> int:
            """Return every failed observation, including omitted report rows."""
            return sum(rule.failure_count for rule in self.rules)

        @property
        def failures(self) -> Sequence[Assessment]:
            """Return every failed observation with its rule definition."""
            return [
                Assessment(
                    definition=rule.definition,
                    observation=observation,
                    verdict=Verdict.FAIL,
                )
                for rule in self.rules
                for observation in rule.failures
            ]

        @property
        def finding_count(self) -> int:
            """Return every finding, including omitted report rows."""
            return sum(rule.finding_count for rule in self.rules)

        @property
        def selection(self) -> list[RuleDefinition]:
            """Return selected definitions in catalog order."""
            return [rule.definition for rule in self.rules]

        @property
        def unassessed_count(self) -> int:
            """Return observations without a complete policy."""
            return sum(rule.unassessed for rule in self.rules)


Assessment = _JudgmentModels.Assessment
RuleJudgment = _JudgmentModels.RuleJudgment
Verdicts = _JudgmentModels.Verdicts

Verdicts.model_rebuild(_types_namespace={"Assessment": Assessment, "RuleJudgment": RuleJudgment})
