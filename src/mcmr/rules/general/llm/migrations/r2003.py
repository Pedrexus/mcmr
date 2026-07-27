from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import MigrationFact


class CompatibilityWindow(StrEnum):
    ADEQUATE = auto()
    NARROW = auto()
    BROKEN = auto()
    NOT_REQUIRED = auto()
    UNCERTAIN = auto()


@rule
async def compatibility_window(
    subject: MigrationFact,
    backend: ClassificationBackend,
) -> CompatibilityWindow:
    """Judge whether a migration preserves the required compatibility window.

    Definition
    ----------
    Ask the selected judgment backend for four independently cited compatibility facts and reduce
    them through a fixed decision table. Compare old and new read and write behavior, deployment
    overlap, backfill duration, queued work, replicas, and rollback duration.

    Evidence
    --------
    The frozen bundle cites version matrices, schemas, read and write behavior, durations, and
    removal gates. Missing, duplicate, conflicting, or uncited answers remain `unknown` and reduce
    to `uncertain`.

    Exceptions
    ----------
    A proven atomic offline migration may not require coexistence when no old process can run.

    Examples
    --------
    An additive field tolerated by both versions through rollout and rollback is `adequate`. A new
    writer emitting values rejected by the old reader is `broken`.

    References
    ----------
    Cites "Evolutionary Database Design"
    Cites "Refactoring Databases", transition patterns
    Cites "The Site Reliability Workbook", canarying releases
    """
    return await backend.classify(
        subject,
        category=CompatibilityWindow,
        instructions=(
            "Ask the selected judgment backend for four independently cited compatibility"
            "facts and reduce them through a fixed decision table. Compare old and new"
            "read and write behavior, deployment overlap, backfill duration, queued work,"
            "replicas, and rollback duration."
        ),
    )
