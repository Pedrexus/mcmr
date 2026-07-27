from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import BenchmarkFact


class BenchmarkQuality(StrEnum):
    REPRESENTATIVE = auto()
    MICRO_ONLY = auto()
    UNCONTROLLED = auto()
    STALE = auto()
    NOT_NEEDED = auto()
    UNCERTAIN = auto()


@rule
async def benchmark_quality(
    subject: BenchmarkFact,
    backend: ClassificationBackend,
) -> BenchmarkQuality:
    """Judge whether a benchmark supports the decision made from it.

    Definition
    ----------
    Compare the decision, workload distribution, data size, environment, warmup, repetitions,
    variance, baseline, resources, end-to-end effects, and recency.

    Evidence
    --------
    Findings cite benchmark code, commands, environments, samples, statistics, and the claimed
    decision.

    Exceptions
    ----------
    Focused microbenchmarks are valid for isolated mechanism questions with bounded claims.

    Examples
    --------
    A representative service workload with controlled comparisons is `representative`. Timing one
    parser token and claiming end-to-end speedup is `micro_only`.

    References
    ----------
    Cites "Systems Performance"
    Cites "The Python Standard Library", timeit
    Cites "Beyond the Basic Stuff with Python", Measuring Performance and Big O
    """
    return await backend.classify(
        subject,
        category=BenchmarkQuality,
        instructions=(
            "Compare the decision, workload distribution, data size, environment, warmup,"
            "repetitions, variance, baseline, resources, end-to-end effects, and recency."
        ),
    )
