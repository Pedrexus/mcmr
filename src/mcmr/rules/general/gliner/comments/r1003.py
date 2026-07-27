from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import CommentFact


class CommentIntent(StrEnum):
    RATIONALE = auto()
    CONTRACT = auto()
    WARNING = auto()
    RESTATEMENT = auto()
    TODO = auto()
    DISABLED_CODE = auto()
    HISTORICAL = auto()
    UNCERTAIN = auto()


@rule
async def comment_intent(
    subject: CommentFact,
    backend: ClassificationBackend,
) -> CommentIntent:
    """Classify why a comment exists with a local bounded model.

    Definition
    ----------
    GLiNER2 compares the comment with the code it governs and chooses one closed intent.
    Predictions below the configured confidence observation become uncertain. Separate
    deterministic rules may prefilter exact syntax when they are enabled by the caller.

    Evidence
    --------
    The finding retains the model confidence and source path.

    Exceptions
    ----------
    Comment usefulness, truth, and staleness require separate evidence and rules.

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
    return await backend.classify(
        subject,
        category=CommentIntent,
        instructions=(
            "GLiNER2 compares the comment with the code it governs and chooses one closed"
            "intent. Predictions below the configured confidence observation become"
            "uncertain. Separate deterministic rules may prefilter exact syntax when they"
            "are enabled by the caller."
        ),
    )
