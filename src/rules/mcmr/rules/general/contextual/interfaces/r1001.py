from enum import StrEnum, auto

import polars as pl

from ..... import Category, rule
from .....execution import ClassificationBackend
from .....execution.queries import ModelQuery
from .....facts import ClassFact
from .....table import Table


class _InterfaceSegregation(StrEnum):
    FOCUSED = auto()
    BLOATED = auto()
    FRAGMENTED = auto()
    FACADE = auto()
    UNCERTAIN = auto()


@rule(
    "ALL-INTE1001",
    policy=Category.outcomes(
        _InterfaceSegregation,
        good={_InterfaceSegregation.FACADE, _InterfaceSegregation.FOCUSED},
        neutral={_InterfaceSegregation.UNCERTAIN},
    ),
)
def interface_segregation(
    subject: Table[ClassFact],
    backend: ClassificationBackend,
) -> ModelQuery[_InterfaceSegregation]:
    """Judge whether clients depend on a focused contract.

    Definition
    ----------
    Compare interface members with the subsets used by each client and implemented meaningfully by
    each provider. Small size alone does not establish a focused interface. The criteria
    independently establish client usage, provider support, distinct subsets, split cost, and a
    facade boundary.

    Evidence
    --------
    Findings cite members, client usage matrices, implementations, and candidate contract splits.

    Exceptions
    ----------
    A cohesive facade may expose several operations when clients understand one unified capability.

    Examples
    --------
    A storage protocol forcing read-only clients to implement deletion is `bloated`. Separate read
    and write protocols are `focused` when their clients differ.

    References
    ----------
    Cites "Design Principles and Design Patterns", SOLID interface segregation principle
    Cites "Building Maintainable Software", write small interfaces
    Cites "Fluent Python", Interfaces, Protocols, and ABCs
    """
    return backend.classification(
        subject,
        category=_InterfaceSegregation,
        instructions=interface_segregation.instructions,
    ).where(
        (pl.col("methods.length") > 0)
        & ((pl.col("direct_subclasses.length") > 0) | pl.col("is_protocol"))
        & ~pl.col("is_test"),
        requires=("methods.length", "direct_subclasses.length", "is_protocol", "is_test"),
    )
