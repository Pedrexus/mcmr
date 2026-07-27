from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import BackupFact


class BackupRecency(StrEnum):
    CURRENT = auto()
    STALE = auto()
    MISSING = auto()
    NOT_REQUIRED = auto()
    UNCERTAIN = auto()


@rule
async def backup_recency(
    subject: BackupFact,
    backend: ClassificationBackend,
) -> BackupRecency:
    """Judge whether available backups satisfy the recovery point objective.

    Definition
    ----------
    Compare critical state inventory, backup completion, replication lag, log retention, current
    time, recovery point objective, reconstruction path, and known backup failures.

    Evidence
    --------
    Findings cite state, completed backups, retained logs, lags, failures, times, and objectives.

    Exceptions
    ----------
    Reconstructable state may use a timed and verified reconstruction point instead of a backup.

    Examples
    --------
    A successful snapshot and retained logs within a fifteen-minute objective are `current`. A
    daily snapshot is `stale` for a one-hour objective even when storage reports it as healthy.

    References
    ----------
    Cites "Site Reliability Engineering", disaster recovery
    Cites "NIST SP 800-34, Contingency Planning Guide"
    Cites "PostgreSQL documentation", continuous archiving
    """
    return await backend.classify(
        subject,
        category=BackupRecency,
        instructions=(
            "Compare critical state inventory, backup completion, replication lag, log"
            "retention, current time, recovery point objective, reconstruction path, and"
            "known backup failures."
        ),
    )
