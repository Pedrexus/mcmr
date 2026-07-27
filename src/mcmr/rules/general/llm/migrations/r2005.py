from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import MigrationFact


class MigrationReversibility(StrEnum):
    REVERSIBLE = auto()
    RECOVERABLE = auto()
    FALSE_REVERSAL = auto()
    IRREVERSIBLE = auto()
    NOT_REQUIRED = auto()
    UNCERTAIN = auto()


@rule
async def migration_reversibility(
    subject: MigrationFact,
    backend: ClassificationBackend,
) -> MigrationReversibility:
    """Judge whether a migration is genuinely reversible or recoverable.

    Definition
    ----------
    Ask the selected judgment backend for five independently cited recovery facts and reduce them
    through a fixed decision table. Compare information loss, retained representations, inverse
    transforms, compatibility, backups, replay, recovery timing, and rehearsal evidence.

    Evidence
    --------
    The frozen bundle cites transforms, retained state, down paths, backups, replays, rehearsals,
    and accepted loss. Missing, duplicate, conflicting, or uncited answers remain `unknown` and
    reduce to `uncertain`.

    Exceptions
    ----------
    Authorized one-way migrations may be `recoverable` when verified alternate recovery meets the
    declared objectives.

    Examples
    --------
    Retaining old values until inverse conversion is verified can be `reversible`. Recreating a
    dropped column without its values is a `false_reversal`.

    References
    ----------
    Cites "Refactoring Databases", transition patterns
    Cites "Evolutionary Database Design"
    Cites "NIST SP 800-34, Contingency Planning Guide"
    """
    return await backend.classify(
        subject,
        category=MigrationReversibility,
        instructions=(
            "Ask the selected judgment backend for five independently cited recovery"
            "facts and reduce them through a fixed decision table. Compare information"
            "loss, retained representations, inverse transforms, compatibility, backups,"
            "replay, recovery timing, and rehearsal evidence."
        ),
    )
