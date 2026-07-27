from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import RecoveryPlanFact


class RecoveryObjectiveFit(StrEnum):
    MEETS = auto()
    RPO_RISK = auto()
    RTO_RISK = auto()
    BOTH_AT_RISK = auto()
    UNDECLARED = auto()
    NOT_REQUIRED = auto()
    UNCERTAIN = auto()


@rule
async def recovery_objective_fit(
    subject: RecoveryPlanFact,
    backend: ClassificationBackend,
) -> RecoveryObjectiveFit:
    """Judge whether verified recovery capability fits declared objectives.

    Definition
    ----------
    Compare approved recovery point and time objectives with credible recovery points, restore
    durations, dependency recovery, scale, parallelism, detection delay, and recent rehearsals.

    Evidence
    --------
    Findings cite objectives, recovery points, durations, dependencies, rehearsals, and gaps.

    Exceptions
    ----------
    Noncritical components may inherit system objectives when their recovery is included.

    Examples
    --------
    A fifteen-minute recovery point and a forty-minute full restore against one-hour objectives is
    `meets`. The same restore is `rto_risk` when dependency recovery adds two hours. A backup
    running daily against a one-hour recovery point objective is `rpo_risk`, and a system with no
    approved objectives at all is `undeclared`.

    References
    ----------
    Cites "Site Reliability Engineering", disaster recovery
    Cites "NIST SP 800-34, Contingency Planning Guide"
    Cites "ISO 22301", business continuity concepts
    """
    return await backend.classify(
        subject,
        category=RecoveryObjectiveFit,
        instructions=(
            "Compare approved recovery point and time objectives with credible recovery"
            "points, restore durations, dependency recovery, scale, parallelism,"
            "detection delay, and recent rehearsals."
        ),
    )
