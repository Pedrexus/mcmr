from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import SecurityBoundaryFact


class VulnerabilityResponseReadiness(StrEnum):
    READY = auto()
    PARTIAL = auto()
    ABSENT = auto()
    STALE = auto()
    NOT_REQUIRED = auto()
    UNCERTAIN = auto()


@rule
async def vulnerability_response_readiness(
    subject: SecurityBoundaryFact,
    backend: ClassificationBackend,
) -> VulnerabilityResponseReadiness:
    """Judge whether a project can receive and resolve vulnerability reports.

    Definition
    ----------
    Compare private reporting, scope, ownership, triage, response objectives, advisory creation,
    coordinated disclosure, patch production, release, notification, and retrospective evidence.

    Evidence
    --------
    Findings cite security policy, contacts, owners, objectives, advisory tools, release path, and
    previous response evidence.

    Exceptions
    ----------
    Private transient components may inherit a clearly identified parent response process.

    Examples
    --------
    A current private reporting path with an owner and tested advisory-to-release workflow is
    `ready`. A stale email address with no patch owner is `partial` or absent.

    References
    ----------
    Cites "OpenSSF Best Practices Badge", vulnerability reporting criteria
    Cites "Open Source Project Security Baseline"
    Cites "GitHub documentation", security advisory
    """
    return await backend.classify(
        subject,
        category=VulnerabilityResponseReadiness,
        instructions=(
            "Compare private reporting, scope, ownership, triage, response objectives,"
            "advisory creation, coordinated disclosure, patch production, release,"
            "notification, and retrospective evidence."
        ),
    )
