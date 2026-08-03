from enum import StrEnum, auto

import polars as pl

from ..... import Category, rule
from .....execution import ClassificationBackend
from .....execution.queries import ModelQuery
from .....facts import ClassFact
from .....table import Table


class _AbstractionQuality(StrEnum):
    USEFUL = auto()
    LEAKY = auto()
    PREMATURE = auto()
    WRONG = auto()
    MISSING = auto()
    UNCERTAIN = auto()


@rule(
    "ALL-ABST1001",
    policy=Category.outcomes(
        _AbstractionQuality,
        good={_AbstractionQuality.USEFUL},
        neutral={_AbstractionQuality.UNCERTAIN},
    ),
)
def abstraction_quality(
    subject: Table[ClassFact], backend: ClassificationBackend
) -> ModelQuery[_AbstractionQuality]:
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
    return backend.classification(
        subject,
        category=_AbstractionQuality,
        instructions=abstraction_quality.instructions,
    ).where(
        (pl.col("methods.length") >= 2) & ~pl.col("is_test"),
        requires=("methods.length", "is_test"),
    )
