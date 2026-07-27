from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import AbstractionFact


class AbstractionQuality(StrEnum):
    USEFUL = auto()
    LEAKY = auto()
    PREMATURE = auto()
    WRONG = auto()
    MISSING = auto()
    UNCERTAIN = auto()


@rule
async def abstraction_quality(
    subject: AbstractionFact, backend: ClassificationBackend
) -> AbstractionQuality:
    """Judge whether an abstraction reduces total system complexity.

    Definition
    ----------
    Compare interface size, hidden complexity, caller knowledge, change reasons, duplication,
    failure behavior, and plausible direct alternatives.
    The criteria separately observe hidden complexity, interface stability, leaked caller
    knowledge, demonstrated variation, independent change causes, and unowned shared knowledge.

    Evidence
    --------
    Findings cite interface members, callers, leaked details, changes, and duplicated knowledge.

    Exceptions
    ----------
    Thin protocol adapters can remain shallow when they isolate an external boundary.

    Examples
    --------
    A storage interface hiding retries and provider details is `useful`. A generic manager whose
    callers pass provider-specific flags is `leaky`.

    References
    ----------
    Cites "A Philosophy of Software Design", deep modules
    Cites "Practical Object-Oriented Design"
    Cites "Clean Architecture"
    """
    return await backend.classify(
        subject,
        category=AbstractionQuality,
        instructions=(
            "Compare interface size, hidden complexity, caller knowledge, change reasons,"
            "duplication, failure behavior, and plausible direct alternatives. The"
            "criteria separately observe hidden complexity, interface stability, leaked"
            "caller knowledge, demonstrated variation, independent change causes, and"
            "unowned shared knowledge."
        ),
    )
