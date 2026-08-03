from patos import FrozenModel
from pydantic import NonNegativeInt


class EngineCountFields:
    """Group flat engine counters by catalog and execution work."""

    class Catalog(FrozenModel):
        """Count selected rules, lanes, skips, facts, and executions."""

        rule_count: NonNegativeInt = 0
        rule_counts_by_lane: dict[str, NonNegativeInt] = {}
        rule_executions_by_lane: dict[str, NonNegativeInt] = {}
        skipped_rules: list[str] = []
        fact_count: NonNegativeInt = 0
        rule_execution_count: NonNegativeInt = 0

    class Execution(Catalog):
        """Count queries, observations, provider reads, and fixes."""

        table_query_count: NonNegativeInt = 0
        table_queries_by_family: dict[str, NonNegativeInt] = {}
        observation_count: NonNegativeInt = 0
        provider_read_count: NonNegativeInt = 0
        fix_count: NonNegativeInt = 0
        fix_candidate_count: NonNegativeInt = 0
