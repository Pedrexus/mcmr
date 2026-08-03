from time import perf_counter_ns
from typing import TYPE_CHECKING

import polars as pl
from patos import FrozenModel, Runtime

from ...checking.evaluations import TableEvaluationReport, TableRuleSummary
from ...domain.contracts import EngineStats
from ...table import RepositoryTables
from ..schema.values import frame_value
from .planning import CompiledRule, ResolvedRule, RuleCompiler
from .results import QueryEvaluations

if TYPE_CHECKING:
    from collections.abc import Sequence


class QueryExecution(FrozenModel):
    """Execute one resolved lazy rule graph and materialize its bounded report."""

    tables: Runtime[RepositoryTables]
    rules: list[ResolvedRule]
    failure_limit: int | None

    @staticmethod
    def collect(
        compiled: Sequence[CompiledRule],
        failure_limit: int | None,
    ) -> tuple[pl.DataFrame, QueryEvaluations]:
        """Collect summaries first, then evidence only for retained failures."""
        if not compiled:
            return pl.DataFrame(), QueryExecution._evaluations(pl.DataFrame())
        summaries, failures = QueryExecution._primary(compiled, failure_limit)
        if failures.is_empty():
            return summaries, QueryExecution._evaluations(failures)
        findings, rewrites, nodes, imports = QueryExecution._details(compiled, failures)
        return summaries, QueryEvaluations(
            failures=failures,
            findings=findings,
            fix_rewrites=rewrites,
            fix_nodes=nodes,
            fix_imports=imports,
        )

    def report(self) -> TableEvaluationReport:
        """Compile, collect, and adapt the lazy graph at one execution boundary."""
        started = perf_counter_ns()
        compiled, planning_nanoseconds = self._compiled()
        summary_rows, evaluations, execution_nanoseconds = self._collected(compiled)
        summaries = self._summaries(summary_rows)
        fix_candidates, fix_nanoseconds = self._fix_candidates(summaries)
        timings = self._timings(
            planning=planning_nanoseconds,
            execution=execution_nanoseconds,
            fixes=fix_nanoseconds,
            total=perf_counter_ns() - started,
        )
        stats = self._stats(summaries, fix_candidates, timings)
        return self._report(evaluations, summaries, stats)

    @staticmethod
    def _details(
        compiled: Sequence[CompiledRule],
        failures: pl.DataFrame,
    ) -> list[pl.DataFrame]:
        selected = failures.select("rule", "fact_id", "fact_order").lazy()
        rewrites = QueryExecution._rewrites(compiled, selected)
        selected_rewrites = rewrites.select("rule", "fact_id", "rewrite_order", "fact_order")
        return pl.collect_all(
            [
                QueryExecution._findings(compiled, selected),
                rewrites,
                QueryExecution._nodes(compiled, selected_rewrites),
                QueryExecution._imports(compiled, selected_rewrites),
            ]
        )

    @staticmethod
    def _evaluations(failures: pl.DataFrame) -> QueryEvaluations:
        """Return evaluations whose optional detail relations are empty."""
        return QueryEvaluations(
            failures=failures,
            findings=pl.DataFrame(),
            fix_rewrites=pl.DataFrame(),
            fix_nodes=pl.DataFrame(),
            fix_imports=pl.DataFrame(),
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
    def _report(
        evaluations: QueryEvaluations,
        summaries: list[TableRuleSummary],
        stats: EngineStats,
    ) -> TableEvaluationReport:
        return TableEvaluationReport(
            summaries=summaries,
            failures=evaluations.evaluations(),
            stats=stats,
        )

    @staticmethod
    def _rewrites(compiled: Sequence[CompiledRule], selected: pl.LazyFrame) -> pl.LazyFrame:
        return (
            pl.concat([rule.fix_rewrites for rule in compiled], how="vertical")
            .join(selected, on=["rule", "fact_id"], how="inner")
            .sort("fact_order", "rule_order", "rewrite_order")
        )

    @staticmethod
    def _summaries(collected: pl.DataFrame) -> list[TableRuleSummary]:
        return [
            TableRuleSummary(
                rule=frame_value(collected, index, "rule", str),
                observation_count=frame_value(
                    collected,
                    index,
                    "observation_count",
                    int,
                ),
                unassessed_count=frame_value(collected, index, "unassessed_count", int),
                failure_count=frame_value(collected, index, "failure_count", int),
                finding_count=frame_value(collected, index, "finding_count", int),
            )
            for index in range(collected.height)
        ]

    @staticmethod
    def _timings(
        *,
        planning: int,
        execution: int,
        fixes: int,
        total: int,
    ) -> EngineStats:
        return EngineStats(
            planning_nanoseconds=planning,
            execution_nanoseconds=execution,
            fix_planning_nanoseconds=fixes,
            total_nanoseconds=total,
        )

    def _collected(
        self,
        compiled: Sequence[CompiledRule],
    ) -> tuple[pl.DataFrame, QueryEvaluations, int]:
        started = perf_counter_ns()
        summaries, evaluations = self.collect(compiled, self.failure_limit)
        return summaries, evaluations, perf_counter_ns() - started

    def _compiled(self) -> tuple[list[CompiledRule], int]:
        started = perf_counter_ns()
        compiled = [
            RuleCompiler(
                prepared=rule.prepared,
                query=rule.query,
                policy=rule.policy,
                accepted_paths=rule.accepted_paths,
                rule_order=order,
            ).compile()
            for order, rule in enumerate(self.rules)
        ]
        return compiled, perf_counter_ns() - started

    def _fix_candidates(self, summaries: Sequence[TableRuleSummary]) -> tuple[int, int]:
        started = perf_counter_ns()
        count = sum(
            summary.observation_count * rule.fix_count
            for summary, rule in zip(summaries, self.rules, strict=True)
        )
        return count, perf_counter_ns() - started

    def _queries_by_family(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for rule in self.rules:
            name = rule.prepared.primary_family.__name__
            counts[name] = counts.get(name, 0) + 1
        return counts

    def _stats(
        self,
        summaries: Sequence[TableRuleSummary],
        fix_candidate_count: int,
        timings: EngineStats,
    ) -> EngineStats:
        return EngineStats(
            rule_count=len(self.rules),
            fact_count=sum(
                table.frame(next(iter(table.relation_type))).height
                for table in self.tables.values()
            ),
            rule_execution_count=len(self.rules),
            table_query_count=len(self.rules),
            table_queries_by_family=self._queries_by_family(),
            observation_count=sum(summary.observation_count for summary in summaries),
            provider_read_count=len(self.tables),
            fix_candidate_count=fix_candidate_count,
            planning_nanoseconds=timings.planning_nanoseconds,
            execution_nanoseconds=timings.execution_nanoseconds,
            fix_planning_nanoseconds=timings.fix_planning_nanoseconds,
            total_nanoseconds=timings.total_nanoseconds,
        )
