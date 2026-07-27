from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import StateFact


class StateOwnership(StrEnum):
    OWNED = auto()
    SHARED = auto()
    LEAKED = auto()
    IMMUTABLE = auto()
    UNCERTAIN = auto()


@rule
async def state_ownership(
    subject: StateFact,
    backend: ClassificationBackend,
) -> StateOwnership:
    """Judge whether mutable state has one clear owner.

    Definition
    ----------
    Trace creation, mutation, aliases, exposure, synchronization, persistence, and lifecycle.
    Shared state is acceptable only when its governing contract remains explicit.

    Evidence
    --------
    Findings cite state declarations, aliases, writers, readers, transitions, and synchronization.

    Exceptions
    ----------
    Deliberate shared caches and framework state may be valid with bounded mutation and ownership.

    Examples
    --------
    Returning an internal mutable list that callers edit is `leaked`. An immutable snapshot updated
    through one repository is `owned`.

    References
    ----------
    Cites "Fluent Python", Object References, Mutability, and Recycling
    Cites "Refactoring", Global Data and Mutable Data
    Cites "Programming Clojure", immutable values and managed state
    """
    return await backend.classify(
        subject,
        category=StateOwnership,
        instructions=(
            "Trace creation, mutation, aliases, exposure, synchronization, persistence,"
            "and lifecycle. Shared state is acceptable only when its governing contract"
            "remains explicit."
        ),
    )
