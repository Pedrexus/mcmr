from collections.abc import Mapping
from contextlib import closing
from functools import partial
from pathlib import Path
from time import perf_counter_ns
from typing import TYPE_CHECKING

from anyio.to_thread import run_sync
from patos import FrozenModel, Runtime
from pydantic import JsonValue

from ...domain.contracts import RuleDependency, RuleScope
from ...execution.providers import ExternalEvidence
from ...facts import ModuleFact, buildable
from ...table import AnalysisSession, RepositoryTables
from .contracts.coverage import TableCoverage
from .contracts.judgment import JudgmentSink
from .runner import TableRunner

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence, Set

    from ...checking.engine.batch import RuleBatch
    from ...checking.evaluations import PreparedRule
    from ...domain.policy import Policy
    from ...facts import Fact


class TableExecution(FrozenModel):
    """Execute connected table graphs and release each graph after its rules finish."""

    root: Path
    suffixes: list[str]
    dependencies: Runtime[Mapping[type, RuleDependency]]
    accumulator: Runtime[JudgmentSink]
    provider_settings: Mapping[str, Mapping[str, JsonValue]] = {}

    async def run(
        self,
        typed_families: Collection[type[Fact]],
        *,
        batches: Sequence[RuleBatch],
        fix_counts: Mapping[str, int],
    ) -> TableCoverage:
        """Run each table batch once and report what the repository let the rules reach."""
        evidence = ExternalEvidence.for_repository(self.root, self.provider_settings)
        native_families, external_families, eager = self._families(
            typed_families, evidence, batches
        )
        session, ordered, elapsed = await self._session(native_families)
        native, elapsed = await self._native_tables(session, ordered, eager, elapsed=elapsed)
        external = await self._external_tables(external_families, evidence, native)
        available = native_families | set(external)
        coverage = TableCoverage(languages=self._observed_languages(native))
        for batch in batches:
            runnable = [rule for rule in batch.rules if rule.families <= available]
            if not runnable:
                continue
            required = {family for rule in runnable for family in rule.families}
            tables, added = await self._tables_for(
                session,
                ordered=ordered,
                native=native,
                external=external,
                required=required,
            )
            coverage.read_families.update(family.__name__ for family in required)
            elapsed += added
            applicable = [rule for rule in runnable if rule.applies_to(tables)]
            if applicable:
                await self._run_rules(tables, applicable, fix_counts)
                coverage.runnable.update(rule.path for rule in applicable)
        coverage.kernel = session.kernel_stats(elapsed)
        return coverage

    @staticmethod
    def _language_probe(batches: Sequence[RuleBatch]) -> set[type[Fact]]:
        """Return the per-module family a language-scoped selection reads its own scope from."""
        narrowable = any(
            rule.scope is not RuleScope.GENERAL for batch in batches for rule in batch.rules
        )
        return {ModuleFact} if narrowable else set()

    @staticmethod
    def _observed_languages(native: RepositoryTables) -> set[str]:
        """Return the languages the per-module probe found, when this run needed it."""
        return native[ModuleFact].observed_languages if ModuleFact in native else set()

    @staticmethod
    def _raise_marker_error(name: str, seen: Collection[str]) -> None:
        """Raise the exact native marker contract violation."""
        if name in seen:
            raise RuntimeError(f"the native session repeated table {name}")
        raise RuntimeError(f"the native session returned unexpected table {name}")

    async def _external_tables(
        self,
        external: Collection[type[Fact]],
        evidence: ExternalEvidence,
        dependencies: RepositoryTables,
    ) -> RepositoryTables:
        """Collect requested external families into one request-local relation set."""
        return await evidence.tables(external, dependencies) if external else RepositoryTables()

    def _families(
        self,
        typed: Collection[type[Fact]],
        evidence: ExternalEvidence,
        batches: Sequence[RuleBatch],
    ) -> tuple[set[type[Fact]], set[type[Fact]], set[type[Fact]]]:
        """Partition rule inputs from the families this run materializes before any rule reads."""
        native = {family for family in typed if not family.external_evidence}
        external = set(typed) - native
        required = evidence.requirements(external)
        provider_native = required & set(buildable().values())
        unavailable = required - provider_native - evidence.provided
        if unavailable:
            names = ", ".join(sorted(family.__name__ for family in unavailable))
            raise RuntimeError(f"MCMR fact providers require unavailable families {names}")
        eager = provider_native | self._language_probe(batches)
        return native | eager, external, eager

    async def _native_tables(
        self,
        session: AnalysisSession,
        ordered: Sequence[type[Fact]],
        required: Collection[type[Fact]],
        *,
        elapsed: int,
    ) -> tuple[RepositoryTables, int]:
        """Materialize provider inputs and carry forward native execution time."""
        tables = RepositoryTables()
        for family in [item for item in ordered if item in required]:
            started = perf_counter_ns()
            tables.add(await run_sync(session.table, family))
            elapsed += perf_counter_ns() - started
        return tables, elapsed

    async def _ordered_families(
        self,
        session: AnalysisSession,
        expected_families: Collection[type[Fact]],
    ) -> list[type[Fact]]:
        """Validate native table markers and return their delivery order."""
        expected = {family.__name__: family for family in expected_families}
        ordered: list[type[Fact]] = []
        seen: set[str] = set()
        with closing(session.table_markers()) as markers:
            while (name := await run_sync(partial(next, markers, None))) is not None:
                if name in seen or name not in expected:
                    self._raise_marker_error(name, seen)
                ordered.append(expected[name])
                seen.add(name)
        if missing := set(expected) - seen:
            raise RuntimeError(
                f"the native session omitted fact families {', '.join(sorted(missing))}"
            )
        return ordered

    def _policies(self, rules: Sequence[PreparedRule]) -> dict[str, Policy | None]:
        """Resolve one configured policy for every applicable rule."""
        return {
            rule.path: self.accumulator.policies.policy(
                rule_id=self.accumulator.identity[rule.path].id,
                candidate=self.accumulator.identity[rule.path].policy,
            )
            for rule in rules
        }

    async def _run_rules(
        self,
        tables: RepositoryTables,
        rules: Sequence[PreparedRule],
        fix_counts: Mapping[str, int],
    ) -> None:
        """Run applicable rules and retain their bounded report rows."""
        report = await TableRunner(self.dependencies).report(
            tables,
            rules,
            policies=self._policies(rules),
            fix_counts=fix_counts,
            failure_limit=self.accumulator.remaining_failure_limit,
        )
        self.accumulator.add_table(
            stats=report.stats,
            summaries=report.summaries,
            failures=report.failures,
        )

    async def _session(
        self,
        native: Collection[type[Fact]],
    ) -> tuple[AnalysisSession, list[type[Fact]], int]:
        """Open native delivery and retain its validated family order."""
        started = perf_counter_ns()
        session = await run_sync(
            partial(
                AnalysisSession,
                self.root,
                suffixes=self.suffixes,
                typed_families=sorted(native, key=lambda family: family.__name__),
            )
        )
        elapsed = perf_counter_ns() - started
        return session, await self._ordered_families(session, native), elapsed

    async def _tables_for(
        self,
        session: AnalysisSession,
        *,
        ordered: Sequence[type[Fact]],
        native: RepositoryTables,
        external: RepositoryTables,
        required: Set[type[Fact]],
    ) -> tuple[RepositoryTables, int]:
        """Materialize one connected family set and measure native delivery."""
        tables = RepositoryTables()
        elapsed = 0
        for family in [item for item in ordered if item in required]:
            if family in native:
                tables.add(native[family])
                continue
            started = perf_counter_ns()
            table = await run_sync(session.table, family)
            tables.add(table)
            elapsed += perf_counter_ns() - started
        for family in sorted(required & set(external), key=lambda item: item.__name__):
            tables.add(external[family])
        return tables, elapsed
