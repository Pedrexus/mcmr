from collections.abc import Callable
from functools import cached_property
from typing import TYPE_CHECKING

from patos import FrozenModel, Runtime

from ...domain.contracts import Finding, Observation, RuleValue
from .answer import Evaluation

if TYPE_CHECKING:
    from ...facts import SourceSpan


class DeferredEvaluation(FrozenModel):
    """Carry one scalar answer and defer source evidence until a failure needs it."""

    rule: str
    value: RuleValue
    finding_count: int
    supplier: Runtime[Callable[[], Evaluation]]

    @cached_property
    def evaluation(self) -> Evaluation:
        """Materialize and retain the complete evaluation at most once."""
        return self.supplier()

    @property
    def fact(self) -> str:
        """Return the fact identity from the deferred complete evaluation."""
        return self.evaluation.fact

    @property
    def findings(self) -> list[Finding]:
        """Return findings from the deferred complete evaluation."""
        return self.evaluation.findings

    @property
    def span(self) -> SourceSpan:
        """Return the source span from the deferred complete evaluation."""
        return self.evaluation.span

    def observation(self) -> Observation:
        """Materialize the public observation only after the complete evaluation."""
        return self.evaluation.observation()
