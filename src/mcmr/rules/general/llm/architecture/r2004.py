from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import ClassFact


class MixedClassResponsibilities(StrEnum):
    COHESIVE = auto()
    MIXED = auto()
    INTENTIONAL_COORDINATOR = auto()
    UNCERTAIN = auto()


@rule
async def mixed_class_responsibilities(
    subject: ClassFact,
    backend: ClassificationBackend,
) -> MixedClassResponsibilities:
    """Judge whether one class owns unrelated responsibilities.

    Definition
    ----------
    Compare methods, state clusters, collaborators, tests, and change history with a closed
    responsibility rubric. The criteria establish independent change causes, separate member
    clusters, one domain outcome, and a deliberate coordination boundary.

    Evidence
    --------
    Findings cite method clusters, state, callers, tests, and relevant changes.

    Exceptions
    ----------
    Facades, application services, and composition objects may intentionally coordinate.

    Examples
    --------
    A class that prices orders and also renders HTML is `mixed`. A `CheckoutService` coordinating a
    pricing collaborator and a payment collaborator is an `intentional_coordinator`. A class whose
    methods all read one cluster of state is `cohesive`.

    References
    ----------
    Adapts Pylint R0902 too-many-instance-attributes
    Cites "Agile Software Development", single responsibility principle
    Cites "A Philosophy of Software Design", chapter 10
    """
    return await backend.classify(
        subject,
        category=MixedClassResponsibilities,
        instructions=(
            "Compare methods, state clusters, collaborators, tests, and change history"
            "with a closed responsibility rubric. The criteria establish independent"
            "change causes, separate member clusters, one domain outcome, and a"
            "deliberate coordination boundary."
        ),
    )
