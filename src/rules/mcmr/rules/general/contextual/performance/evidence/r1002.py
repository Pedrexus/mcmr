from enum import StrEnum, auto

from ...... import Category, rule
from ......execution import ClassificationBackend
from ......execution.queries import ModelQuery
from ......facts import PerformanceDecisionFact
from ......table import Table


class _OptimizationJustification(StrEnum):
    SUPPORTED = auto()
    UNSUPPORTED = auto()
    REGRESSION = auto()
    NOT_APPLICABLE = auto()
    UNCERTAIN = auto()


@rule(
    "ALL-PERF1002",
    policy=Category.outcomes(
        _OptimizationJustification,
        good={_OptimizationJustification.NOT_APPLICABLE, _OptimizationJustification.SUPPORTED},
        neutral={_OptimizationJustification.UNCERTAIN},
    ),
)
def optimization_justification(
    subject: Table[PerformanceDecisionFact],
    backend: ClassificationBackend,
) -> ModelQuery[_OptimizationJustification]:
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
    return backend.classification(
        subject,
        category=_OptimizationJustification,
        instructions=optimization_justification.instructions,
    )
