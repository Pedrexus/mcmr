from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import CloneGroupFact


class SemanticDuplication(StrEnum):
    SHARED_KNOWLEDGE = auto()
    SIMILAR_SHAPE = auto()
    INTENTIONAL_BOUNDARY = auto()
    UNCERTAIN = auto()


@rule
async def semantic_duplication(
    subject: CloneGroupFact,
    backend: ClassificationBackend,
) -> SemanticDuplication:
    """Judge whether similar code duplicates shared knowledge.

    Definition
    ----------
    Compare normalized code, ownership, callers, and change reasons. Classify duplication
    as shared knowledge only when the copies should change together. The criteria separately
    establish the same fact, coordinated change, independent ownership, and deliberate boundaries.

    Evidence
    --------
    Findings cite every compared region and the ownership or history facts used.

    Exceptions
    ----------
    Independent contracts and explicit adapters may retain similar code.

    Examples
    --------
    Two validators implementing the same tax rule are `shared_knowledge`, because a change to the
    rule has to reach both. Similar request parsing at two independent protocol boundaries is an
    `intentional_boundary`. Two loops that normalize different domains through the same shape are
    `similar_shape`.

    References
    ----------
    Cites "The Pragmatic Programmer", DRY principle
    Cites "A Philosophy of Software Design", chapter 6
    Cites "Refactoring Guru", duplicate code smell
    """
    return await backend.classify(
        subject,
        category=SemanticDuplication,
        instructions=(
            "Compare normalized code, ownership, callers, and change reasons. Classify"
            "duplication as shared knowledge only when the copies should change together."
            "The criteria separately establish the same fact, coordinated change,"
            "independent ownership, and deliberate boundaries."
        ),
    )
