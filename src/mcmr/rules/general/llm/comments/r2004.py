from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import CommentFact


class CommentAccuracy(StrEnum):
    CURRENT = auto()
    STALE = auto()
    AMBIGUOUS = auto()
    HISTORICAL = auto()
    UNCERTAIN = auto()


@rule
async def comment_accuracy(
    subject: CommentFact,
    backend: ClassificationBackend,
) -> CommentAccuracy:
    """Judge whether a comment remains accurate beside the current system.

    Definition
    ----------
    Compare comment claims with nearby code, tests, configuration, contracts, and relevant
    history. Intent classification alone does not establish truth. The criteria separately ask
    whether the claim matches, is contradicted, is verifiable, or preserves marked relevant
    history.

    Evidence
    --------
    Findings cite the comment, claimed behavior, contradictory or supporting facts, and history.

    Exceptions
    ----------
    Historical rationale may remain useful when clearly marked and still relevant.

    Examples
    --------
    A comment saying retries occur three times is `stale` when configuration now allows five. A
    note explaining a protocol workaround remains `current` while that constraint exists.

    References
    ----------
    Cites "Clean Code", Comments
    Cites "A Philosophy of Software Design", comments and documentation
    Cites "The Pragmatic Programmer", documentation and knowledge drift
    """
    return await backend.classify(
        subject,
        category=CommentAccuracy,
        instructions=(
            "Compare comment claims with nearby code, tests, configuration, contracts,"
            "and relevant history. Intent classification alone does not establish truth."
            "The criteria separately ask whether the claim matches, is contradicted, is"
            "verifiable, or preserves marked relevant history."
        ),
    )
