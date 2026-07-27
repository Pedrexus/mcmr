from ..... import rule
from .....facts import OperationalRiskFact
from .....models import Percentage


@rule
def observability_coverage(
    subject: OperationalRiskFact,
) -> Percentage:
    """Measure observability coverage over declared operational risks.

    Definition
    ----------
    Divide risks and critical paths with an actionable configured signal by all declared
    operational risks and critical paths and return the percentage. More telemetry does not
    increase the score unless it supports detection or diagnosis.

    Evidence
    --------
    Findings link each risk to logs, metrics, traces, alerts, dashboards, and runbooks. The value
    is the percentage of declared risks and critical paths carrying an actionable signal.

    Exceptions
    ----------
    Libraries without runtime ownership may define only diagnostic hooks and contracts.

    Examples
    --------
    Four observable critical paths among five declared paths produce `80`. High-volume
    debug logs without a linked risk do not improve the percentage.

    References
    ----------
    Cites "Site Reliability Engineering", monitoring distributed systems
    Cites "OpenTelemetry documentation"
    Cites "Observability Engineering"
    """
    return subject.risks.coverage("actionable_signal")
