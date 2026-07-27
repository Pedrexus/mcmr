from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import MigrationFact


class MigrationSafety(StrEnum):
    SAFE = auto()
    IRREVERSIBLE = auto()
    COUPLED = auto()
    UNVERIFIED = auto()
    NOT_APPLICABLE = auto()
    UNCERTAIN = auto()


@rule
async def migration_safety(
    subject: MigrationFact,
    backend: ClassificationBackend,
) -> MigrationSafety:
    """Judge whether a persistent-state migration can be rolled out safely.

    Definition
    ----------
    Ask the selected judgment backend for six independently cited migration facts and reduce them
    through a fixed decision table. Compare compatibility, data volume, locks, duration, backfill,
    observability, recovery, ownership, and deployment ordering.

    Evidence
    --------
    The frozen bundle cites schemas, scripts, estimates, rehearsals, checks, deployment steps, and
    recovery. Missing, duplicate, conflicting, or uncited answers remain `unknown` and reduce to
    `uncertain`.

    Exceptions
    ----------
    Explicit one-way migrations may be accepted when information loss and recovery are authorized.

    Examples
    --------
    An expand, migrate, verify, and contract sequence can be `safe`. Dropping populated state
    without verified recovery is `irreversible`.

    References
    ----------
    Cites "Evolutionary Database Design"
    Cites "The Site Reliability Workbook", canarying releases
    Cites "Refactoring Databases", transition patterns
    """
    return await backend.classify(
        subject,
        category=MigrationSafety,
        instructions=(
            "Ask the selected judgment backend for six independently cited migration"
            "facts and reduce them through a fixed decision table. Compare compatibility,"
            "data volume, locks, duration, backfill, observability, recovery, ownership,"
            "and deployment ordering."
        ),
    )
