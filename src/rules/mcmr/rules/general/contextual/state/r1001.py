from enum import StrEnum, auto

import polars as pl

from ..... import Category, rule
from .....execution import ClassificationBackend
from .....execution.queries import ModelQuery
from .....facts import ClassFact
from .....table import Table


class _StateOwnership(StrEnum):
    OWNED = auto()
    SHARED = auto()
    LEAKED = auto()
    IMMUTABLE = auto()
    UNCERTAIN = auto()


@rule(
    "ALL-STAT1001",
    policy=Category.outcomes(
        _StateOwnership,
        good={_StateOwnership.IMMUTABLE, _StateOwnership.OWNED},
        neutral={_StateOwnership.UNCERTAIN},
    ),
)
def state_ownership(
    subject: Table[ClassFact],
    backend: ClassificationBackend,
) -> ModelQuery[_StateOwnership]:
    """Judge whether mutable state has one clear owner.

    Definition
    ----------
    Trace creation, mutation, aliases, exposure, synchronization, persistence, and lifecycle.
    State several holders reach is still `owned` when one explicit governing contract decides
    every write, whether that contract is a lock, a single writer, or a supplied protocol.
    `shared` names state several holders mutate with no such contract to point at, and `leaked`
    names internal state handed out for any caller to edit.

    Evidence
    --------
    Findings cite state declarations, aliases, writers, readers, transitions, and synchronization.

    Exceptions
    ----------
    Deliberate shared caches and framework state may be valid with bounded mutation and ownership.

    Examples
    --------
    Returning an internal mutable list that callers edit is `leaked`. An immutable snapshot updated
    through one repository is `owned`.

    References
    ----------
    Cites "Fluent Python", Object References, Mutability, and Recycling
    Cites "Refactoring", Global Data and Mutable Data
    Cites "Programming Clojure", immutable values and managed state
    """
    return backend.classification(
        subject,
        category=_StateOwnership,
        instructions=state_ownership.instructions,
    ).where(
        pl.col("has_instance_fields")
        & (
            pl.col("is_exported")
            | (pl.col("importing_modules.length") > 0)
            | (pl.col("direct_subclasses.length") > 0)
        )
        & ~pl.col("is_test"),
        requires=(
            "has_instance_fields",
            "is_exported",
            "importing_modules.length",
            "direct_subclasses.length",
            "is_test",
        ),
    )
