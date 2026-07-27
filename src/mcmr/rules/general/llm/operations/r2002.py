from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import RecoveryPlanFact


class RestoreReadiness(StrEnum):
    VERIFIED = auto()
    UNTESTED = auto()
    INCOMPLETE = auto()
    STALE = auto()
    NOT_REQUIRED = auto()
    UNCERTAIN = auto()


@rule
async def restore_readiness(
    subject: RecoveryPlanFact,
    backend: ClassificationBackend,
) -> RestoreReadiness:
    """Judge whether critical state can be restored within declared objectives.

    Definition
    ----------
    Compare state inventory, backup integrity, encryption, dependencies, procedure, permissions,
    rehearsal, recovery point, recovery time, data volume, and verification.

    Evidence
    --------
    Findings cite state, backups, restore runs, durations, integrity checks, and unmet objectives.

    Exceptions
    ----------
    Reconstructable caches and stateless services may document recreation instead of backup.

    Examples
    --------
    A recent isolated restore meeting integrity and time objectives is `verified`. A daily backup
    never restored is `untested`.

    References
    ----------
    Cites "Site Reliability Engineering", disaster recovery testing
    Cites "NIST SP 800-34, Contingency Planning Guide"
    Cites "PostgreSQL documentation", backup and restore
    """
    return await backend.classify(
        subject,
        category=RestoreReadiness,
        instructions=(
            "Compare state inventory, backup integrity, encryption, dependencies,"
            "procedure, permissions, rehearsal, recovery point, recovery time, data"
            "volume, and verification."
        ),
    )
