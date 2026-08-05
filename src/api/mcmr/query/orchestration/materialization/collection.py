from typing import TYPE_CHECKING

import polars as pl
from patos import Runtime

from .results import QueryEvaluations

if TYPE_CHECKING:
    from collections.abc import Sequence

    from ..planning import CompiledRule


class CollectedRules(QueryEvaluations):
    """Expose collected rule relations for direct inspection."""

    summaries: Runtime[pl.DataFrame]

    @classmethod
    def collect(
        cls,
        compiled: Sequence[CompiledRule],
        failure_limit: int | None,
    ) -> CollectedRules:
        """Collect compiled queries into inspectable eager relations."""
        if not compiled:
            empty = pl.DataFrame()
            return cls(
                summaries=empty,
                failures=empty,
                findings=empty,
                fix_rewrites=empty,
                fix_nodes=empty,
                fix_imports=empty,
            )
        summaries, failures = cls._primary(compiled, failure_limit)
        if failures.is_empty():
            empty = pl.DataFrame()
            return cls(
                summaries=summaries,
                failures=failures,
                findings=empty,
                fix_rewrites=empty,
                fix_nodes=empty,
                fix_imports=empty,
            )
        findings, rewrites, nodes, imports = cls._details(compiled, failures)
        return cls(
            summaries=summaries,
            failures=failures,
            findings=findings,
            fix_rewrites=rewrites,
            fix_nodes=nodes,
            fix_imports=imports,
        )

    @staticmethod
    def _details(
        compiled: Sequence[CompiledRule],
        failures: pl.DataFrame,
    ) -> list[pl.DataFrame]:
        selected = failures.select("rule", "fact_id", "fact_order").lazy()
        rewrites = CollectedRules._rewrites(compiled, selected)
        selected_rewrites = rewrites.select("rule", "fact_id", "rewrite_order", "fact_order")
        return pl.collect_all(
            [
                CollectedRules._findings(compiled, selected),
                rewrites,
                CollectedRules._nodes(compiled, selected_rewrites),
                CollectedRules._imports(compiled, selected_rewrites),
            ]
        )

    @staticmethod
    def _findings(compiled: Sequence[CompiledRule], selected: pl.LazyFrame) -> pl.LazyFrame:
        return (
            pl.concat([rule.findings for rule in compiled], how="vertical")
            .join(selected, on=["rule", "fact_id"], how="inner")
            .sort("fact_order", "rule_order", "finding_order")
        )

    @staticmethod
    def _imports(compiled: Sequence[CompiledRule], selected: pl.LazyFrame) -> pl.LazyFrame:
        return (
            pl.concat([rule.fix_imports for rule in compiled], how="vertical")
            .join(selected, on=["rule", "fact_id", "rewrite_order"], how="inner")
            .sort("fact_order", "rule_order", "rewrite_order", "ordinal")
        )

    @staticmethod
    def _nodes(compiled: Sequence[CompiledRule], selected: pl.LazyFrame) -> pl.LazyFrame:
        return (
            pl.concat([rule.fix_nodes for rule in compiled], how="vertical")
            .join(selected, on=["rule", "fact_id", "rewrite_order"], how="inner")
            .sort("fact_order", "rule_order", "rewrite_order", "ordinal")
        )

    @staticmethod
    def _primary(
        compiled: Sequence[CompiledRule],
        failure_limit: int | None,
    ) -> list[pl.DataFrame]:
        summaries = pl.concat([rule.result for rule in compiled], how="vertical")
        failures = pl.concat([rule.failures for rule in compiled], how="vertical").sort(
            "fact_order", "rule_order"
        )
        retained = failures if failure_limit is None else failures.head(failure_limit)
        return pl.collect_all([summaries, retained])

    @staticmethod
    def _rewrites(compiled: Sequence[CompiledRule], selected: pl.LazyFrame) -> pl.LazyFrame:
        return (
            pl.concat([rule.fix_rewrites for rule in compiled], how="vertical")
            .join(selected, on=["rule", "fact_id"], how="inner")
            .sort("fact_order", "rule_order", "rewrite_order")
        )


CollectedRules.model_rebuild(_types_namespace={"Runtime": Runtime})
