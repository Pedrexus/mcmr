from typing import TYPE_CHECKING

from patos import Model

from ...domain.contracts import EngineStats, Observation, RuleLane
from .models import RuleJudgment

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence

    from ...rulebook.catalog import RuleDefinition
    from ..evaluations import DeferredEvaluation, Evaluation, TableRuleSummary


class JudgmentState(Model):
    """Own mutable totals while one judgment streams table results."""

    class Totals(Model):
        """Accumulate compact policy totals for one rule."""

        observations: int = 0
        unassessed: int = 0
        failure_count: int = 0
        finding_count: int = 0

    totals: dict[str, Totals]
    failures: dict[str, list[Observation]]
    retained_failure_count: int = 0
    reached: set[str] = set()
    statistics: EngineStats = EngineStats()

    @classmethod
    def of(cls, definitions: Sequence[RuleDefinition]) -> JudgmentState:
        """Initialize one mutable slot for every selected rule."""
        return cls(
            totals={definition.callable: cls.Totals() for definition in definitions},
            failures={definition.callable: [] for definition in definitions},
        )

    def add_summary(self, summary: TableRuleSummary) -> None:
        """Accumulate one table rule's compact totals."""
        totals = self.totals[summary.rule]
        totals.observations += summary.observation_count
        totals.unassessed += summary.unassessed_count
        totals.failure_count += summary.failure_count
        totals.finding_count += summary.finding_count
        self.reached.add(summary.rule)

    def completed_stats(
        self,
        definitions: Sequence[RuleDefinition],
        runnable: Collection[str],
        *,
        provider_read_count: int,
        fix_count: int,
    ) -> EngineStats:
        """Return final engine totals after the last table batch."""
        return self.statistics.model_copy(
            update={
                "rule_count": len(definitions),
                "rule_counts_by_lane": self.lane_counts(definitions),
                "rule_executions_by_lane": self.lane_executions(definitions, runnable),
                "skipped_rules": [
                    item.id for item in definitions if item.callable not in runnable
                ],
                "provider_read_count": provider_read_count,
                "fix_count": fix_count,
            }
        )

    def lane_counts(self, definitions: Sequence[RuleDefinition]) -> dict[str, int]:
        """Return selected rule counts by execution lane."""
        return {
            lane: sum(definition.lane == lane for definition in definitions) for lane in RuleLane
        }

    def lane_executions(
        self,
        definitions: Sequence[RuleDefinition],
        runnable: Collection[str],
    ) -> dict[str, int]:
        """Return executed rule counts by lane."""
        return {
            lane: sum(
                definition.lane == lane and definition.callable in runnable
                for definition in definitions
            )
            for lane in RuleLane
        }

    def retain(self, result: Evaluation | DeferredEvaluation) -> None:
        """Retain one failed observation for presentation."""
        self.failures[result.rule].append(result.observation())
        self.retained_failure_count += 1

    def rule_judgments(self, definitions: Sequence[RuleDefinition]) -> list[RuleJudgment]:
        """Materialize final per-rule judgments in catalog order."""
        return [
            RuleJudgment(
                definition=definition,
                **self.totals[definition.callable].model_dump(),
                failures=self.failures[definition.callable],
            )
            for definition in definitions
        ]
