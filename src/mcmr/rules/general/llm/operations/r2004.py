from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import RecoveryPlanFact


class RestoreVerification(StrEnum):
    VERIFIED = auto()
    PARTIAL = auto()
    OBSOLETE = auto()
    UNTESTED = auto()
    NOT_REQUIRED = auto()
    UNCERTAIN = auto()


@rule
async def restore_verification(
    subject: RecoveryPlanFact,
    backend: ClassificationBackend,
) -> RestoreVerification:
    """Judge whether backups have been verified through a representative restore.

    Definition
    ----------
    Compare restore execution, isolation, current formats, data volume, dependencies, credentials,
    integrity checks, application usability, observed duration, and unresolved failures.

    Evidence
    --------
    Findings cite restore runs, environments, versions, volumes, checks, durations, and failures.

    Exceptions
    ----------
    A verified deterministic reconstruction may replace restore testing for reconstructable state.

    Examples
    --------
    An isolated current-volume restore that passes integrity and application checks is `verified`.
    A checksum over backup files without restoration is `untested`.

    References
    ----------
    Cites "Site Reliability Engineering", disaster recovery testing
    Cites "NIST SP 800-34, Contingency Planning Guide"
    Cites "PostgreSQL documentation", backup and restore
    """
    return await backend.classify(
        subject,
        category=RestoreVerification,
        instructions=(
            "Compare restore execution, isolation, current formats, data volume,"
            "dependencies, credentials, integrity checks, application usability, observed"
            "duration, and unresolved failures."
        ),
    )
