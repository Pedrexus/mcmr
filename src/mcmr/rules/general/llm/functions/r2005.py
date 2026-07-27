from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import FunctionFact


class AbstractionLevel(StrEnum):
    COHESIVE = auto()
    MIXED = auto()
    BOUNDARY = auto()
    UNCERTAIN = auto()


@rule
async def abstraction_level(
    subject: FunctionFact,
    backend: ClassificationBackend,
) -> AbstractionLevel:
    """Judge whether a function stays at one useful level of abstraction.

    Definition
    ----------
    Compare the function name, orchestration, domain operations, low-level mechanics, and
    extracted helpers. Mixed means a reader must repeatedly switch between policy and mechanism.
    The criteria independently establish a shared intent level, interleaving, repeated switching,
    and a deliberate boundary purpose.

    Evidence
    --------
    Findings cite the function body, callees, names, and the level assigned to each operation.

    Exceptions
    ----------
    Composition roots and small adapters may coordinate levels when the boundary remains obvious.

    Examples
    --------
    `publish_report` that validates policy and also hand-builds HTTP frames is `mixed`. A
    composition root that wires a report service to an HTTP adapter is a `boundary`. A function
    whose every statement names a domain operation is `cohesive`.

    References
    ----------
    Cites "Clean Code", Functions
    Cites "A Philosophy of Software Design", different layer different abstraction
    Cites "Refactoring", Extract Function
    """
    return await backend.classify(
        subject,
        category=AbstractionLevel,
        instructions=(
            "Compare the function name, orchestration, domain operations, low-level"
            "mechanics, and extracted helpers. Mixed means a reader must repeatedly"
            "switch between policy and mechanism. The criteria independently establish a"
            "shared intent level, interleaving, repeated switching, and a deliberate"
            "boundary purpose."
        ),
    )
