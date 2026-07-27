from statistics import median
from time import perf_counter_ns
from typing import TYPE_CHECKING

import anyio
from pydantic import Field

from .bases import FrozenFlexModel
from .catalog import Catalog
from .discovery import RuleModuleDiscovery
from .engine import MockEngine
from .facts import Fact, SourceSpan
from .models import EngineReport, FixContract, FloorReport, RuleContract, fact_type

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


class FloorBenchmark(FrozenFlexModel):
    """Measure the lower bound of the Python rule framework."""

    samples: int = Field(default=9, gt=0)
    fact_count: int = Field(default=1000, gt=0)

    def run(self) -> FloorReport:
        """Run bounded repeated samples and summarize their median timings."""
        discovery_started = perf_counter_ns()
        catalog = Catalog(modules=RuleModuleDiscovery().modules)
        definitions = catalog.definitions
        cold_discovery_nanoseconds = perf_counter_ns() - discovery_started
        warm_discovery_started = perf_counter_ns()
        _ = catalog.definitions
        warm_discovery_nanoseconds = perf_counter_ns() - warm_discovery_started
        workspace = self.workspace(catalog.rules)
        reports = anyio.run(self.measure, catalog.rules, catalog.fixes, workspace)
        return FloorReport(
            samples=self.samples,
            fact_count=sum(len(facts) for facts in workspace.values()),
            rule_count=len(definitions),
            cold_discovery_nanoseconds=cold_discovery_nanoseconds,
            warm_discovery_nanoseconds=warm_discovery_nanoseconds,
            median_planning_nanoseconds=int(
                median(item.stats.planning_nanoseconds for item in reports)
            ),
            median_execution_nanoseconds=int(
                median(item.stats.execution_nanoseconds for item in reports)
            ),
            median_fix_planning_nanoseconds=int(
                median(item.stats.fix_planning_nanoseconds for item in reports)
            ),
            median_total_nanoseconds=int(median(item.stats.total_nanoseconds for item in reports)),
        )

    async def measure(
        self,
        rules: list[RuleContract],
        fixes: list[FixContract],
        workspace: Mapping[type[Fact], Sequence[Fact]],
    ) -> list[EngineReport]:
        """Run every sample inside one AnyIO event loop."""
        engine = MockEngine(rules=rules, fixes=fixes)
        return [await engine.run(workspace) for _ in range(self.samples)]

    def workspace(self, rules: list[RuleContract]) -> dict[type[Fact], list[Fact]]:
        """Build at least one synthetic fact for every requested provider stream."""
        required = {fact_type(rule.hints[next(iter(rule.signature.parameters))]) for rule in rules}
        facts_per_type = max(1, self.fact_count // len(required))
        return {
            required_type: [
                required_type.model_construct(
                    key=f"{required_type.__name__}:{index}",
                    span=SourceSpan(path=f"module_{index}.py"),
                )
                for index in range(facts_per_type)
            ]
            for required_type in required
        }
