from patos import FrozenModel, Runtime
from pydantic import JsonValue

from .stats import KernelStats


class KernelAnswer(FrozenModel):
    """Hold one kernel response envelope before its payload is narrowed."""

    version: int
    facts: Runtime[dict[str, list[JsonValue]]] = {}
    graph: Runtime[JsonValue] = None
    stats: KernelStats = KernelStats()
