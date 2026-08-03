from enum import StrEnum, auto

import polars as pl

from ..... import Category, rule
from .....execution import ClassificationBackend
from .....execution.queries import ModelQuery
from .....facts import CallFact
from .....table import Table


class _DiagnosticContext(StrEnum):
    ACTIONABLE = auto()
    SPARSE = auto()
    NOISY = auto()
    UNSAFE = auto()
    UNCERTAIN = auto()


@rule(
    "ALL-OBSE1001",
    policy=Category.outcomes(
        _DiagnosticContext,
        good={_DiagnosticContext.ACTIONABLE},
        neutral={_DiagnosticContext.UNCERTAIN},
    ),
)
def diagnostic_context(
    subject: Table[CallFact],
    backend: ClassificationBackend,
) -> ModelQuery[_DiagnosticContext]:
    """Judge whether telemetry carries useful and safe diagnostic context.

    Definition
    ----------
    Compare operational questions, event identity, outcome, correlation, dimensions, errors,
    cardinality, privacy, volume, and downstream search or aggregation needs.

    Evidence
    --------
    Findings cite signal schemas, examples, operational questions, costs, and sensitive fields.

    Exceptions
    ----------
    Hot paths may emit compact signals when correlation links to richer context elsewhere.

    Examples
    --------
    A failed request signal with operation, outcome, trace, and safe account class is `actionable`.
    Repeating full payloads on every step is `noisy` and unsafe.

    References
    ----------
    Cites "OpenTelemetry Semantic Conventions"
    Cites "Observability Engineering", context-rich debugging
    Cites "Site Reliability Engineering", monitoring distributed systems
    """
    telemetry = (
        r"(?i)(?:^|\.)(?:debug|info|warn|warning|error|exception|critical|log|metric|"
        r"counter|histogram|gauge|trace|span|emit|observe|increment|set_attribute)$"
    )
    return backend.classification(
        subject,
        category=_DiagnosticContext,
        instructions=diagnostic_context.instructions,
    ).where(
        pl.col("qualified_name").str.contains(telemetry) & ~pl.col("is_test"),
        requires=("qualified_name", "is_test"),
    )
