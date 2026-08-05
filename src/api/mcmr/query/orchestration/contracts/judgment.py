from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from ....checking.evaluations import DeferredEvaluation, Evaluation, TableRuleSummary
    from ....domain.contracts import EngineStats
    from ....domain.policy import RulePolicies
    from ....rulebook.catalog import RuleDefinition


class JudgmentSink(Protocol):
    """Receive table judgments without coupling query execution to one session."""

    @property
    def identity(self) -> Mapping[str, RuleDefinition]: ...

    @property
    def policies(self) -> RulePolicies: ...

    @property
    def remaining_failure_limit(self) -> int | None: ...

    def add_table(
        self,
        *,
        stats: EngineStats,
        summaries: Sequence[TableRuleSummary],
        failures: Iterable[Evaluation | DeferredEvaluation],
    ) -> None: ...
