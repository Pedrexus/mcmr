from collections.abc import Iterable

from patos import FrozenModel, Runtime

from ....domain.contracts import EngineStats
from ..answer import Evaluation
from ..deferred import DeferredEvaluation
from .summary import TableRuleSummary


class TableEvaluationReport(FrozenModel):
    """Return compact policy totals and only the table rows a report may retain."""

    summaries: list[TableRuleSummary]
    failures: Runtime[Iterable[Evaluation | DeferredEvaluation]]
    stats: EngineStats
