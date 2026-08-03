import pydantic

from .fields import KernelStatsFields

type KernelArgument = str | bool | list[str]


class KernelStats(KernelStatsFields):
    """Measure what the kernel did to answer one request."""

    total_nanoseconds: pydantic.NonNegativeInt = 0
    protocol_validation_nanoseconds: pydantic.NonNegativeInt = 0
    fact_validation_nanoseconds: pydantic.NonNegativeInt = 0
    node_count: pydantic.NonNegativeInt = 0
    edge_count: pydantic.NonNegativeInt = 0
    repository_fingerprint: str = ""


KernelStats.model_rebuild(_types_namespace={"pydantic": pydantic})
