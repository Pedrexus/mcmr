from patos import FrozenModel
from pydantic import PositiveInt


class FloorReportFields:
    """Group flat floor measurements by setup and terminal timing."""

    class Planning(FrozenModel):
        """Retain sample, corpus, discovery, and planning measurements."""

        samples: PositiveInt
        fact_count: PositiveInt
        rule_count: PositiveInt
        cold_discovery_nanoseconds: PositiveInt
        warm_discovery_nanoseconds: PositiveInt
        median_planning_nanoseconds: PositiveInt
        median_execution_nanoseconds: PositiveInt

    class Completion(Planning):
        """Retain fix planning and total execution measurements."""

        median_fix_planning_nanoseconds: PositiveInt
        median_total_nanoseconds: PositiveInt
