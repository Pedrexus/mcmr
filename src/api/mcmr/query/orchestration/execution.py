from collections.abc import Mapping
from contextlib import closing
from functools import partial
from pathlib import Path
from time import perf_counter_ns
from typing import TYPE_CHECKING

from anyio.to_thread import run_sync
from patos import FrozenModel, Runtime
from pydantic import JsonValue

from ...domain.contracts import RuleDependency
from ...execution.providers import ExternalEvidence
from ...kernel import buildable
from ...table import AnalysisSession, RepositoryTables
from ..runtime import TableRunner
from .contracts import JudgmentSink
from .environment import BatchEnvironment
from .partition import FamilyPartition

if TYPE_CHECKING:
    from collections.abc import Collection, Sequence, Set

    from ...checking.engine.batch import RuleBatch
    from ...checking.evaluations import PreparedRule
    from ...domain.policy import Policy
    from ...facts import Fact
    from ...kernel import KernelStats


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
    ) -> tuple[KernelStats, set[str], int]:
        """Run each table batch once and return native and rule coverage totals."""
        partition = self._families(typed_families)
        environment, elapsed = await self._setup(partition, fix_counts)
        runnable_paths: set[str] = set()
        read_families: set[type[Fact]] = set()
        for batch in batches:
            read, runnable, added = await self._run_batch(batch, environment)
            read_families.update(read)
            runnable_paths.update(runnable)
            elapsed += added
        return environment.session.kernel_stats(elapsed), runnable_paths, len(read_families)

    @staticmethod
    def _raise_marker_error(name: str, seen: Collection[str]) -> None:
        """Raise the exact native marker contract violation."""
        if name in seen:
            raise RuntimeError(f"the native session repeated table {name}")
        raise RuntimeError(f"the native session returned unexpected table {name}")

    async def _external_tables(self, partition: FamilyPartition) -> RepositoryTables:
        """Collect requested external families into one request-local relation set."""
        return (
            await ExternalEvidence.for_repository(self.root, self.provider_settings).tables(
                partition.external
            )
            if partition.external
            else RepositoryTables()
        )

    def _families(self, typed: Collection[type[Fact]]) -> FamilyPartition:
        """Partition requested families between native and external providers."""
        native_names = buildable().keys()
        native = {family for family in typed if family.__name__ in native_names}
        return FamilyPartition(native=native, external=set(typed) - native)

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

    async def _run_batch(
        self,
        batch: RuleBatch,
        environment: BatchEnvironment,
    ) -> tuple[set[type[Fact]], set[str], int]:
        """Run one connected batch when all of its table families are available."""
        runnable = [rule for rule in batch.rules if rule.families <= environment.available]
        if not runnable:
            return set(), set(), 0
        required = {family for rule in runnable for family in rule.families}
        tables, elapsed = await self._tables_for(environment, required)
        applicable = [rule for rule in runnable if rule.applies_to(tables)]
        if not applicable:
            return required, set(), elapsed
        await self._run_rules(tables, applicable, environment.fix_counts)
        return required, {rule.path for rule in applicable}, elapsed

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
        partition: FamilyPartition,
    ) -> tuple[AnalysisSession, list[type[Fact]], int]:
        """Open native delivery and retain its validated family order."""
        started = perf_counter_ns()
        session = await run_sync(
            partial(
                AnalysisSession,
                self.root,
                suffixes=self.suffixes,
                typed_families=sorted(family.__name__ for family in partition.native),
            )
        )
        elapsed = perf_counter_ns() - started
        return session, await self._ordered_families(session, partition.native), elapsed

    async def _setup(
        self,
        partition: FamilyPartition,
        fix_counts: Mapping[str, int],
    ) -> tuple[BatchEnvironment, int]:
        """Open native delivery and collect the requested external tables."""
        session, ordered, elapsed = await self._session(partition)
        external = await self._external_tables(partition)
        return (
            BatchEnvironment(
                session=session,
                ordered=ordered,
                external=external,
                available=partition.native | set(external),
                fix_counts=fix_counts,
            ),
            elapsed,
        )

    async def _tables_for(
        self,
        environment: BatchEnvironment,
        required: Set[type[Fact]],
    ) -> tuple[RepositoryTables, int]:
        """Materialize one connected family set and measure native delivery."""
        tables = RepositoryTables()
        elapsed = 0
        for family in [item for item in environment.ordered if item in required]:
            started = perf_counter_ns()
            tables.add(await run_sync(environment.session.table, family))
            elapsed += perf_counter_ns() - started
        for family in sorted(required & set(environment.external), key=lambda item: item.__name__):
            tables.add(environment.external[family])
        return tables, elapsed
