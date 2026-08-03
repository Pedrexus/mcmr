from enum import StrEnum, auto

import polars as pl

from ..... import Category, rule
from .....execution import ClassificationBackend
from .....execution.queries import ModelQuery
from .....facts import OverrideFact
from .....table import Table


class _Substitutability(StrEnum):
    PRESERVED = auto()
    NARROWED = auto()
    WEAKENED = auto()
    REFUSED = auto()
    UNCERTAIN = auto()


@rule(
    "ALL-CLAS1002",
    policy=Category.outcomes(
        _Substitutability,
        good={_Substitutability.PRESERVED},
        neutral={_Substitutability.UNCERTAIN},
    ),
)
def substitutability(
    subject: Table[OverrideFact],
    backend: ClassificationBackend,
) -> ModelQuery[_Substitutability]:
    """Judge whether an implementation preserves its declared type contract.

    Definition
    ----------
    Compare one resolved direct inheritance link. The declared and inherited members establish
    callable shape, binding, defaults, decorators, asynchronous behavior, and exact member source.
    Report `narrowed`, `refused`, or `weakened` only when those supplied declarations affirmatively
    establish the contract break. This is an observable contract check rather than proof about
    every possible runtime behavior. Matching callable shape with no refusal or contradictory
    behavior in the supplied bodies is `preserved`, even when implementations return different
    representations. Use `uncertain` only when a specific supplied declaration is incomplete or
    contradictory, and name the missing fact in the reasoning.

    Evidence
    --------
    Findings cite the inherited contract and the overriding declaration that establishes the
    verdict.

    Exceptions
    ----------
    Explicitly narrower new protocols are not subtypes and should be assessed as separate APIs.

    Examples
    --------
    A read-only repository that raises for the inherited `save` method refuses its contract.
    A cached repository with a compatible signature and no visible refusal is `preserved`. An
    override may return a different concrete representation when the supplied contract does not
    prohibit it.

    References
    ----------
    Cites "A Behavioral Notion of Subtyping"
    Cites "Design Principles and Design Patterns", SOLID Liskov substitution principle
    Cites "Refactoring", Refused Bequest
    """
    return backend.classification(
        subject,
        category=_Substitutability,
        instructions=substitutability.instructions,
    ).where(
        (pl.col("depth") == 1) & (pl.col("overridden_member_count") > 0),
        requires=("depth", "overridden_member_count"),
    )
