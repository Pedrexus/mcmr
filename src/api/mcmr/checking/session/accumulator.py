from itertools import islice
from typing import TYPE_CHECKING

from .models import Verdicts
from .state import JudgmentState

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable, Sequence

    from ...domain.contracts import EngineStats
    from ...domain.policy import RulePolicies
    from ...kernel import KernelStats
    from ...rulebook.catalog import RuleDefinition
    from ...rulebook.scope import LanguageScope
    from ..evaluations import DeferredEvaluation, Evaluation, TableRuleSummary


class JudgmentAccumulator:
    """Fold streamed engine batches into bounded per-rule judgments."""

    def __init__(
        self,
        policies: RulePolicies,
        definitions: Sequence[RuleDefinition],
        failure_limit: int | None,
    ) -> None:
        self.policies = policies
        self.definitions = list(definitions)
        self.identity = {definition.callable: definition for definition in definitions}
        self.state = JudgmentState.of(definitions)
        self.failure_limit = failure_limit

    @property
    def remaining_failure_limit(self) -> int | None:
        """Return how many more failures a bounded report may retain."""
        return (
            None
            if self.failure_limit is None
            else max(0, self.failure_limit - self.state.retained_failure_count)
        )

    def add_table(
        self,
        *,
        stats: EngineStats,
        summaries: Sequence[TableRuleSummary],
        failures: Iterable[Evaluation | DeferredEvaluation],
    ) -> None:
        """Fold table-native totals and bounded failed rows."""
        self.state.statistics = self.state.statistics.accumulated(stats)
        for summary in summaries:
            self.state.add_summary(summary)
        remaining = self.remaining_failure_limit
        retained = failures if remaining is None else islice(failures, remaining)
        for result in retained:
            self.state.retain(result)

    def finish(
        self,
        kernel: KernelStats,
        *,
        runnable: Collection[str],
        scope: LanguageScope,
        provider_read_count: int,
    ) -> Verdicts:
        """Return the complete judgment over the rules this repository has a language for."""
        definitions = scope.selected(self.definitions)
        engine = self.state.completed_stats(
            definitions,
            runnable,
            provider_read_count=provider_read_count,
            fix_count=sum(bool(definition.fixes) for definition in definitions),
        )
        return Verdicts(
            policies=self.policies,
            rules=self.state.rule_judgments(definitions),
            failure_limit=self.failure_limit,
            kernel=kernel,
            engine=engine,
        )
