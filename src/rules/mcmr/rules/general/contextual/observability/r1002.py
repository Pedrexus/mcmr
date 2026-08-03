from enum import StrEnum, auto

from ..... import Category, rule
from .....execution import ClassificationBackend
from .....execution.queries import ModelQuery
from .....facts import OperationalRiskFact
from .....table import Table


class _OperationalRiskCoverage(StrEnum):
    """Classify whether telemetry can answer declared operational risks."""

    ACTIONABLE = auto()
    GAPS = auto()
    NOISY = auto()
    UNSAFE = auto()
    UNCERTAIN = auto()


@rule(
    "ALL-OBSE1002",
    policy=Category.outcomes(
        _OperationalRiskCoverage,
        good={_OperationalRiskCoverage.ACTIONABLE},
        neutral={_OperationalRiskCoverage.UNCERTAIN},
    ),
)
def operational_risk_coverage(
    subject: Table[OperationalRiskFact],
    backend: ClassificationBackend,
) -> ModelQuery[_OperationalRiskCoverage]:
    """Judge whether telemetry answers each declared operational risk.

    Definition
    ----------
    Compare critical paths, failure modes, diagnostic questions, signals, and ownership. A risk is
    actionable only when the retained signals can answer the questions needed to distinguish its
    likely failure modes without unsafe or indiscriminate collection.

    Evidence
    --------
    Findings cite each risk, its critical path, failure modes, diagnostic questions, signals, and
    owner rather than a provider-supplied actionability verdict.

    Exceptions
    ----------
    A signal may link to richer correlated context elsewhere. Low-risk paths may need fewer signals
    when the reason is explicit and the remaining questions still have reliable answers.

    Examples
    --------
    A payment risk with latency, outcome, dependency, and correlation signals that answer its
    timeout and rejection questions is `actionable`. A risk naming several failures but no signal
    that distinguishes them is `gaps`.

    References
    ----------
    Cites "Observability Engineering", debugging from unknowns
    Cites "Site Reliability Engineering", monitoring distributed systems
    Cites "OpenTelemetry documentation"
    """
    return backend.classification(
        subject,
        category=_OperationalRiskCoverage,
        instructions=operational_risk_coverage.instructions,
    )
