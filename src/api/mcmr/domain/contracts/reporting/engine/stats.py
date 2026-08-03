from typing import Annotated

from pydantic import Field

from .counts import EngineCounts

type Nanoseconds = Annotated[int, Field(ge=0)]


class EngineStats(EngineCounts):
    """Measure time performed by the table query engine beside its counts."""

    planning_nanoseconds: Nanoseconds = 0
    execution_nanoseconds: Nanoseconds = 0
    fix_planning_nanoseconds: Nanoseconds = 0
    total_nanoseconds: Nanoseconds = 0

    def accumulated(self, other: EngineStats) -> EngineStats:
        """Add one streamed batch without repeating catalog-wide cardinalities."""
        fix_planning = self.fix_planning_nanoseconds + other.fix_planning_nanoseconds
        return EngineStats(
            fact_count=self.fact_count + other.fact_count,
            rule_execution_count=self.rule_execution_count + other.rule_execution_count,
            table_query_count=self.table_query_count + other.table_query_count,
            table_queries_by_family=self._table_queries(other),
            observation_count=self.observation_count + other.observation_count,
            fix_candidate_count=self.fix_candidate_count + other.fix_candidate_count,
            planning_nanoseconds=self.planning_nanoseconds + other.planning_nanoseconds,
            execution_nanoseconds=self.execution_nanoseconds + other.execution_nanoseconds,
            fix_planning_nanoseconds=fix_planning,
            total_nanoseconds=self.total_nanoseconds + other.total_nanoseconds,
        )

    def _table_queries(self, other: EngineStats) -> dict[str, int]:
        """Merge table family counts from one streamed batch."""
        families = self.table_queries_by_family.keys() | other.table_queries_by_family.keys()
        return {
            name: self.table_queries_by_family.get(name, 0)
            + other.table_queries_by_family.get(name, 0)
            for name in families
        }
