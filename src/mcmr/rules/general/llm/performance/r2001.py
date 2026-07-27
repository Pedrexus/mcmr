from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import PerformanceDecisionFact


class ProfilingEvidence(StrEnum):
    SUFFICIENT = auto()
    STALE = auto()
    INCOMPLETE = auto()
    ABSENT = auto()
    NOT_NEEDED = auto()
    UNCERTAIN = auto()


@rule
async def profiling_evidence(
    subject: PerformanceDecisionFact,
    backend: ClassificationBackend,
) -> ProfilingEvidence:
    """Judge whether a performance decision has adequate profiling evidence.

    Definition
    ----------
    Check workload, environment, baseline, profiler, measured resource, bottleneck, and
    recency before accepting performance evidence.

    Evidence
    --------
    Findings cite profiles, commands, hardware, workloads, baselines, and timestamps.

    Exceptions
    ----------
    Removing obviously dead work can be justified without a full profile when behavior is proven.

    Examples
    --------
    A saved profile over the production workload is `sufficient`. A microbenchmark from an old
    implementation is `stale` for a current system claim.

    References
    ----------
    Cites "Systems Performance"
    Cites "The Python Standard Library", profiling
    """
    return await backend.classify(
        subject,
        category=ProfilingEvidence,
        instructions=(
            "Check workload, environment, baseline, profiler, measured resource,"
            "bottleneck, and recency before accepting performance evidence."
        ),
    )
