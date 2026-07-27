from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import FailurePathFact


class RecoveryBoundary(StrEnum):
    CAPABLE = auto()
    PREMATURE = auto()
    MISSING = auto()
    EXCESSIVE = auto()
    UNCERTAIN = auto()


@rule
async def recovery_boundary(
    subject: FailurePathFact,
    backend: ClassificationBackend,
) -> RecoveryBoundary:
    """Judge whether failures are handled at a capable boundary.

    Definition
    ----------
    Compare failure kinds, retry or fallback authority, transaction scope, user boundary,
    propagation, translation, and corrupted-state risk for each handler. The criteria independently
    establish authority, concrete action, hidden failure, a missing boundary policy, and unsafe
    broad recovery.

    Evidence
    --------
    Findings cite protected operations, caught types, recovery actions, callers, and outcomes.

    Exceptions
    ----------
    Top-level processes may catch broadly to report and terminate safely without claiming recovery.

    Examples
    --------
    A request boundary translating a domain error is `capable`. A repository swallowing every
    exception and returning `None` is `premature`.

    References
    ----------
    Cites "Clean Code", Error Handling
    Cites "The Python Tutorial", handling exceptions
    Cites "Release It", stability patterns and failure boundaries
    """
    return await backend.classify(
        subject,
        category=RecoveryBoundary,
        instructions=(
            "Compare failure kinds, retry or fallback authority, transaction scope, user"
            "boundary, propagation, translation, and corrupted-state risk for each"
            "handler. The criteria independently establish authority, concrete action,"
            "hidden failure, a missing boundary policy, and unsafe broad recovery."
        ),
    )
