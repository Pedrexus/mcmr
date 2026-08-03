from enum import StrEnum, auto

import polars as pl
from pydantic import PositiveInt

from ..... import Category, rule
from .....execution import ClassificationBackend
from .....execution.queries import ModelQuery
from .....facts import CommentFact
from .....table import Table


class _CommentIntent(StrEnum):
    RATIONALE = auto()
    CONTRACT = auto()
    WARNING = auto()
    RESTATEMENT = auto()
    TODO = auto()
    DISABLED_CODE = auto()
    HISTORICAL = auto()
    UNCERTAIN = auto()


@rule(
    "ALL-COMM1001",
    policy=Category.outcomes(
        _CommentIntent,
        good={_CommentIntent.RATIONALE, _CommentIntent.CONTRACT, _CommentIntent.WARNING},
        neutral={_CommentIntent.HISTORICAL, _CommentIntent.UNCERTAIN},
    ),
)
def comment_intent(
    subject: Table[CommentFact],
    backend: ClassificationBackend,
    *,
    minimum_tokens: PositiveInt = 3,
) -> ModelQuery[_CommentIntent]:
    """Classify why a comment exists with a local bounded model.

    Definition
    ----------
    Compare the normalized comment text with its bounded preceding and following source. Choose
    exactly one intent from affirmative words and local code. Directives and commented-out source
    are excluded before model execution, as are API documentation and comments shorter than
    `minimum_tokens`. If the local evidence does not establish one intent, return `uncertain`.

    Evidence
    --------
    The finding retains the model confidence and source path.

    Exceptions
    ----------
    Comment usefulness, truth, and staleness require separate evidence and rules. API documentation
    and comments below `minimum_tokens` stay outside this local implementation-comment rule.

    Examples
    --------
    `# Retry because the service closes idle sockets` is `rationale`. `# Values are UTC` is a
    `contract`. `# Increment count` beside `count += 1` is a `restatement`. A prediction the model
    cannot make confidently comes back `uncertain` rather than guessed.

    References
    ----------
    Cites "Clean Code", chapter 4, Good Comments and Bad Comments
    Cites "A Philosophy of Software Design", chapters 12 through 15
    Cites "GLiNER2 documentation", classification tutorial
    """
    return backend.classification(
        subject,
        category=_CommentIntent,
        instructions=comment_intent.instructions,
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
