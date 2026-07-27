from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import TelemetryFact


class DiagnosticContext(StrEnum):
    ACTIONABLE = auto()
    SPARSE = auto()
    NOISY = auto()
    UNSAFE = auto()
    UNCERTAIN = auto()


@rule
async def diagnostic_context(
    subject: TelemetryFact,
    backend: ClassificationBackend,
) -> DiagnosticContext:
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
    return await backend.classify(
        subject,
        category=DiagnosticContext,
        instructions=(
            "Compare operational questions, event identity, outcome, correlation,"
            "dimensions, errors, cardinality, privacy, volume, and downstream search or"
            "aggregation needs."
        ),
    )
