from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import ClassFact


class Substitutability(StrEnum):
    PRESERVED = auto()
    NARROWED = auto()
    WEAKENED = auto()
    REFUSED = auto()
    UNCERTAIN = auto()


@rule
async def substitutability(
    subject: ClassFact,
    backend: ClassificationBackend,
) -> Substitutability:
    """Judge whether an implementation preserves its declared type contract.

    Definition
    ----------
    Compare accepted inputs, returned guarantees, exceptions, state transitions, invariants,
    and caller assumptions across a parent type or protocol and its implementation. The criteria
    answer input acceptance, output guarantees, failure and state behavior, and refused operations
    independently.

    Evidence
    --------
    Findings cite contracts, implementations, overrides, tests, and affected polymorphic callers.

    Exceptions
    ----------
    Explicitly narrower new protocols are not subtypes and should be assessed as separate APIs.

    Examples
    --------
    A read-only repository that raises for the inherited `save` method refuses its contract.
    A cached repository preserving all repository behavior remains substitutable.

    References
    ----------
    Cites "A Behavioral Notion of Subtyping"
    Cites "Design Principles and Design Patterns", SOLID Liskov substitution principle
    Cites "Refactoring", Refused Bequest
    """
    return await backend.classify(
        subject,
        category=Substitutability,
        instructions=(
            "Compare accepted inputs, returned guarantees, exceptions, state transitions,"
            "invariants, and caller assumptions across a parent type or protocol and its"
            "implementation. The criteria answer input acceptance, output guarantees,"
            "failure and state behavior, and refused operations independently."
        ),
    )
