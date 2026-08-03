from enum import StrEnum, auto

import polars as pl
from pydantic import PositiveInt

from ..... import Category, rule
from .....execution import ClassificationBackend
from .....execution.queries import ModelQuery
from .....facts import CloneGroupFact
from .....table import Table


class _SemanticDuplication(StrEnum):
    SHARED_KNOWLEDGE = auto()
    SIMILAR_SHAPE = auto()
    INTENTIONAL_BOUNDARY = auto()
    UNCERTAIN = auto()


@rule(
    "ALL-DUPL1001",
    policy=Category.outcomes(
        _SemanticDuplication,
        good={_SemanticDuplication.INTENTIONAL_BOUNDARY, _SemanticDuplication.SIMILAR_SHAPE},
        neutral={_SemanticDuplication.UNCERTAIN},
    ),
)
def semantic_duplication(
    subject: Table[CloneGroupFact],
    backend: ClassificationBackend,
    *,
    minimum_tokens: PositiveInt = 80,
) -> ModelQuery[_SemanticDuplication]:
    """Judge whether similar code duplicates shared knowledge.

    Definition
    ----------
    Compare the exact source snippets and locations from one structurally normalized clone group.
    Classify it as shared knowledge only when both snippets encode the same domain fact and should
    change together. Similar mechanics with different domain meaning are `similar_shape`.
    Repeated protocol or adapter code whose separation preserves an ownership boundary is
    `intentional_boundary`. Missing ownership or meaning evidence is `uncertain`.
    `minimum_tokens` limits this semantic pass to clones large enough to carry domain meaning.

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
    return backend.classification(
        subject,
        category=_SemanticDuplication,
        instructions=semantic_duplication.instructions,
    ).where(
        pl.col("token_length") >= minimum_tokens,
        requires=("token_length",),
    )
