from statistics import median
from time import perf_counter_ns
from typing import TYPE_CHECKING

from patos import FrozenModel
from pydantic import Field

from ...checking.engine import RuleEngine
from ...domain.contracts import FloorReport
from ...rulebook.catalog import Catalog
from ...rulebook.discovery import RuleModuleDiscovery
from .sample import PlannerSample

if TYPE_CHECKING:
    from collections.abc import Callable

    from ...domain.contracts import RuleContract


class FloorBenchmark(FrozenModel):
    """Measure the lower bound of table catalog planning without repository IO."""

    samples: int = Field(default=9, gt=0)
    fact_count: int = Field(default=1000, gt=0)

    @staticmethod
    def measure(rules: list[RuleContract]) -> PlannerSample:
        """Measure catalog grouping, prepared contracts, and query-fix planning once."""
        started = perf_counter_ns()
        engine = RuleEngine(rules=rules)
        return PlannerSample(
            planning_nanoseconds=FloorBenchmark._elapsed(lambda: engine.families),
            execution_nanoseconds=FloorBenchmark._elapsed(lambda: engine.prepared),
            fix_planning_nanoseconds=FloorBenchmark._elapsed(lambda: engine.fix_counts),
            total_nanoseconds=max(1, perf_counter_ns() - started),
        )

    def run(self) -> FloorReport:
        """Run bounded planner samples and summarize their median timings."""
        discovery_started = perf_counter_ns()
        catalog = Catalog(modules=RuleModuleDiscovery().modules)
        definitions = catalog.definitions
        cold_discovery_nanoseconds = perf_counter_ns() - discovery_started
        warm_discovery_started = perf_counter_ns()
        _ = catalog.definitions
        warm_discovery_nanoseconds = perf_counter_ns() - warm_discovery_started
        reports = [self.measure(catalog.rules) for _ in range(self.samples)]
        family_count = len({family for rule in catalog.rules for _, family in rule.tables})
        return FloorReport(
            samples=self.samples,
            fact_count=max(self.fact_count, family_count),
            rule_count=len(definitions),
            cold_discovery_nanoseconds=cold_discovery_nanoseconds,
            warm_discovery_nanoseconds=warm_discovery_nanoseconds,
            median_planning_nanoseconds=int(median(item.planning_nanoseconds for item in reports)),
            median_execution_nanoseconds=int(
                median(item.execution_nanoseconds for item in reports)
            ),
            median_fix_planning_nanoseconds=int(
                median(item.fix_planning_nanoseconds for item in reports)
            ),
            median_total_nanoseconds=int(median(item.total_nanoseconds for item in reports)),
        )

    @staticmethod
    def _elapsed[Result](operation: Callable[[], Result]) -> int:
        """Measure one eager planner operation in nanoseconds."""
        started = perf_counter_ns()
        operation()
        return max(1, perf_counter_ns() - started)
