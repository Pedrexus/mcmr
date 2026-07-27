from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import PerformanceDecisionFact


class OptimizationJustification(StrEnum):
    SUPPORTED = auto()
    UNSUPPORTED = auto()
    REGRESSION = auto()
    NOT_APPLICABLE = auto()
    UNCERTAIN = auto()


@rule
async def optimization_justification(
    subject: PerformanceDecisionFact,
    backend: ClassificationBackend,
) -> OptimizationJustification:
    """Judge whether an optimization earns its complexity.

    Definition
    ----------
    Compare before and after measurements, workload relevance, correctness, resource tradeoffs,
    readability, and maintenance cost. Missing baseline or profile requires uncertainty.

    Evidence
    --------
    Findings cite benchmark results, profiles, correctness checks, and complexity changes.

    Exceptions
    ----------
    Hard resource limits can justify small gains when the constraint and margin are explicit.

    Examples
    --------
    A simpler implementation that cuts peak memory by half is `supported`. A cache added without a
    measured bottleneck is `unsupported` or uncertain.

    References
    ----------
    Cites "Structured Programming with go to Statements"
    Cites "Systems Performance"
    Cites "A Philosophy of Software Design"
    """
    return await backend.classify(
        subject,
        category=OptimizationJustification,
        instructions=(
            "Compare before and after measurements, workload relevance, correctness,"
            "resource tradeoffs, readability, and maintenance cost. Missing baseline or"
            "profile requires uncertainty."
        ),
    )
