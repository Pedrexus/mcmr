from enum import StrEnum, auto

import polars as pl
from pydantic import PositiveInt

from ..... import Category, rule
from .....execution import ClassificationBackend
from .....execution.queries import ModelQuery
from .....facts import CommentFact
from .....table import Table


class _CommentAccuracy(StrEnum):
    CURRENT = auto()
    STALE = auto()
    AMBIGUOUS = auto()
    HISTORICAL = auto()
    UNCERTAIN = auto()


@rule(
    "ALL-COMM1002",
    policy=Category.outcomes(
        _CommentAccuracy,
        good={_CommentAccuracy.CURRENT, _CommentAccuracy.HISTORICAL},
        neutral={_CommentAccuracy.UNCERTAIN},
    ),
)
def comment_accuracy(
    subject: Table[CommentFact],
    backend: ClassificationBackend,
    *,
    minimum_tokens: PositiveInt = 3,
) -> ModelQuery[_CommentAccuracy]:
    """Judge whether a comment remains accurate beside the current system.

    Definition
    ----------
    Compare the normalized comment claim with its bounded preceding and following source. Mark it
    `current` only when that source affirmatively agrees and `stale` only when it affirmatively
    contradicts the claim. Mark clearly labeled rationale about an earlier constraint as
    `historical`. Use `ambiguous` when the claim has several readings and `uncertain` when the
    bounded evidence cannot verify it. Directives, commented-out source, API documentation, and
    comments shorter than `minimum_tokens` are excluded.

    Evidence
    --------
    Findings cite the comment, claimed behavior, contradictory or supporting facts, and history.

    Exceptions
    ----------
    Historical rationale may remain useful when clearly marked and still relevant. API
    documentation and comments below `minimum_tokens` stay outside this local implementation
    check.

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
    return backend.classification(
        subject,
        category=_CommentAccuracy,
        instructions=comment_accuracy.instructions,
    ).where(
        ~pl.col("is_directive")
        & ~pl.col("is_documentation")
        & ~pl.col("parses_as_source")
        & (pl.col("token_count") >= minimum_tokens)
        & (pl.col("text").str.len_chars() > 0),
        requires=(
            "is_directive",
            "is_documentation",
            "parses_as_source",
            "text",
            "token_count",
        ),
    )
