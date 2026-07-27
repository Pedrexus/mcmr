from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import FailurePathFact


class CleanupSafety(StrEnum):
    SAFE = auto()
    LEAK = auto()
    OVERCLEAN = auto()
    MANAGED = auto()
    UNCERTAIN = auto()


@rule
async def cleanup_safety(
    subject: FailurePathFact,
    backend: ClassificationBackend,
) -> CleanupSafety:
    """Judge whether partial failure preserves resource and state integrity.

    Definition
    ----------
    Trace acquisition, mutation, commit, rollback, cancellation, exceptions, cleanup, and the
    original failure. The rule covers semantic cleanup beyond syntax-level context-manager checks.
    The criteria independently establish complete exits, central ownership, retained state, and
    harmful cleanup.

    Evidence
    --------
    Findings cite acquisition and release paths, transactions, cancellation, and retained state.

    Exceptions
    ----------
    Process-scoped resources may intentionally live until process termination under one owner.

    Examples
    --------
    A transaction context that rolls back on validation failure is `managed`. Acquiring a lease
    before a cancellable await with no guaranteed release is a `leak`. A handler that also tears
    down state the caller still owns is `overclean`.

    References
    ----------
    Cites "Fluent Python", Context Managers and else Blocks
    Cites "The Python Standard Library", contextlib
    Cites "Effective Python", cleanup with context managers
    """
    return await backend.classify(
        subject,
        category=CleanupSafety,
        instructions=(
            "Trace acquisition, mutation, commit, rollback, cancellation, exceptions,"
            "cleanup, and the original failure. The rule covers semantic cleanup beyond"
            "syntax-level context-manager checks. The criteria independently establish"
            "complete exits, central ownership, retained state, and harmful cleanup."
        ),
    )
