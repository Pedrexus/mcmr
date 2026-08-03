from typing import TYPE_CHECKING

import polars as pl
from patos import FrozenModel, Runtime

from ..execution import QueryExecution

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ..planning import CompiledRule


class CollectedRules(FrozenModel):
    """Expose collected rule relations for direct inspection."""

    summaries: Runtime[pl.DataFrame]
    failures: Runtime[pl.DataFrame]
    findings: Runtime[pl.DataFrame]
    fix_rewrites: Runtime[pl.DataFrame]
    fix_nodes: Runtime[pl.DataFrame]
    fix_imports: Runtime[pl.DataFrame]

    @classmethod
    def collect(
        cls,
        compiled: Sequence[CompiledRule],
        failure_limit: int | None,
    ) -> CollectedRules:
        """Collect compiled queries into inspectable eager relations."""
        summaries, evaluations = QueryExecution.collect(list(compiled), failure_limit)
        return cls(summaries=summaries, **evaluations.model_dump())
