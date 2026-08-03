from enum import StrEnum, auto

import polars as pl
from pydantic import PositiveInt

from ...... import Category, rule
from ......execution import ClassificationBackend
from ......execution.queries import ModelQuery
from ......facts import ClassFact
from ......table import Table


class _MixedClassResponsibilities(StrEnum):
    COHESIVE = auto()
    MIXED = auto()
    INTENTIONAL_COORDINATOR = auto()
    UNCERTAIN = auto()


@rule(
    "ALL-ARCH1004",
    policy=Category.outcomes(
        _MixedClassResponsibilities,
        good={
            _MixedClassResponsibilities.COHESIVE,
            _MixedClassResponsibilities.INTENTIONAL_COORDINATOR,
        },
        neutral={_MixedClassResponsibilities.UNCERTAIN},
    ),
)
def mixed_class_responsibilities(
    subject: Table[ClassFact],
    backend: ClassificationBackend,
    *,
    minimum_methods: PositiveInt = 4,
) -> ModelQuery[_MixedClassResponsibilities]:
    """Judge whether one class owns unrelated responsibilities.

    Definition
    ----------
    Compare the exact class source and its independently citable method bodies. Mark it `mixed`
    only when separate method groups implement unrelated domain outcomes. Mark a facade,
    application service, visitor, or composition object `intentional_coordinator` only when its
    supplied source establishes that role. Otherwise use `cohesive` or `uncertain`.
    `minimum_methods` keeps classes with too little surface for a useful comparison out of this
    semantic pass.

    Evidence
    --------
    Findings cite the exact class and method records that establish the responsibility groups.

    Exceptions
    ----------
    Facades, application services, and composition objects may intentionally coordinate. A class
    below `minimum_methods` remains excluded unless the setting is lowered.

    Examples
    --------
    A class that prices orders and also renders HTML is `mixed`. A `CheckoutService` coordinating a
    pricing collaborator and a payment collaborator is an `intentional_coordinator`. A class whose
    methods all read one cluster of state is `cohesive`.

    References
    ----------
    Adapts Pylint R0902 too-many-instance-attributes
    Cites "Agile Software Development", single responsibility principle
    Cites "A Philosophy of Software Design", chapter 10
    """
    return backend.classification(
        subject,
        category=_MixedClassResponsibilities,
        instructions=mixed_class_responsibilities.instructions,
    ).where(
        pl.col("methods.length") >= minimum_methods,
        requires=("methods.length",),
    )
