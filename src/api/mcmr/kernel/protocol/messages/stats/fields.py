from patos import FrozenModel
from pydantic import NonNegativeInt


class KernelStatsFields(FrozenModel):
    """Retain kernel volume and phase timing measurements."""

    file_count: NonNegativeInt = 0
    byte_count: NonNegativeInt = 0
    fact_count: NonNegativeInt = 0
    parse_failure_count: NonNegativeInt = 0
    discovery_nanoseconds: NonNegativeInt = 0
    extraction_nanoseconds: NonNegativeInt = 0
    graph_nanoseconds: NonNegativeInt = 0
