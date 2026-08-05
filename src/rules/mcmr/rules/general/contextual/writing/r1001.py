import polars as pl
from pydantic import PositiveInt

from ..... import Category, rule
from .....execution import ClassificationBackend
from .....execution.queries import ModelQuery
from .....facts import CommentFact
from .....plugins import NonEmptyStr
from .....table import Table
from .contracts import ProseLanguage


@rule(
    "ALL-WRIT1001",
    policy=Category.outcomes(
        ProseLanguage,
        good={ProseLanguage.TARGET},
        neutral={ProseLanguage.UNCERTAIN},
    ),
)
def comment_language(
    subject: Table[CommentFact],
    backend: ClassificationBackend,
    *,
    target_language: NonEmptyStr = "American English",
    minimum_characters: PositiveInt = 24,
) -> ModelQuery[ProseLanguage]:
    """Keep source comments in one configured project language.

    Definition
    ----------
    Classify each substantial comment as `target`, `other`, or `uncertain`. The configured target
    is `target_language`, which defaults to American English. Judge only the natural-language text
    supplied by the comment provider. A directive or commented-out source is not prose. Do not
    guess from a short or ambiguous fragment, a proper name, an identifier, or a code term.

    Evidence
    --------
    Each finding cites the exact comment record, its source range, model confidence, and model
    provenance. `minimum_characters` excludes fragments that language identification models cannot
    distinguish reliably.

    Exceptions
    ----------
    Quoted user text, protocol tokens, names, and required foreign terms can remain when the
    surrounding explanation uses the project language. Configure another target for a repository
    whose readers use another language.

    Examples
    --------
    With the default target, `# Retry after the peer closes the socket` is `target`. A substantial
    Japanese explanation is `other`. `# Tokio` is excluded by the length floor.

    References
    ----------
    Cites "GlotLID", model guidance on confidence and short text
    https://github.com/cisnlp/GlotLID
    Cites "Lingua", language detection for short and mixed-language text
    https://github.com/pemistahl/lingua-py
    """
    instructions = (
        f"{comment_language.instructions}\n\nThe configured target language is {target_language}."
    )
    return backend.classification(
        subject,
        category=ProseLanguage,
        instructions=instructions,
    ).where(
        ~pl.col("is_directive")
        & ~pl.col("parses_as_source")
        & (pl.col("character_count") >= minimum_characters),
        requires=("character_count", "is_directive", "parses_as_source", "text"),
    )
