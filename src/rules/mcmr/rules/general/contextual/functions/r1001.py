from enum import StrEnum, auto

import polars as pl

from ..... import Category, rule
from .....execution import ClassificationBackend
from .....execution.queries import ModelQuery
from .....facts import FunctionFact
from .....table import Table


class AbstractionLevel(StrEnum):
    COHESIVE = auto()
    MIXED = auto()
    BOUNDARY = auto()
    UNCERTAIN = auto()


@rule(
    "ALL-FUNC1001",
    policy=Category.outcomes(
        AbstractionLevel,
        good={AbstractionLevel.BOUNDARY, AbstractionLevel.COHESIVE},
        neutral={AbstractionLevel.UNCERTAIN},
    ),
)
def abstraction_level(
    subject: Table[FunctionFact],
    backend: ClassificationBackend,
) -> ModelQuery[AbstractionLevel]:
    """Judge whether a function stays at one useful level of abstraction.

    Definition
    ----------
    Compare the function name, orchestration, domain operations, low-level mechanics, and
    extracted helpers. Mixed means a reader must repeatedly switch between policy and mechanism.
    The criteria independently establish a shared intent level, interleaving, repeated switching,
    and a deliberate boundary purpose. Small functions are structurally cohesive enough to skip
    model judgment, so candidates need six statements and four behavior operations.

    Evidence
    --------
    Findings cite the function body, callees, names, and the level assigned to each operation.

    Exceptions
    ----------
    Composition roots and small adapters may coordinate levels when the boundary remains obvious.

    Examples
    --------
    `publish_report` that validates policy and also hand-builds HTTP frames is `mixed`. A
    composition root that wires a report service to an HTTP adapter is a `boundary`. A function
    whose every statement names a domain operation is `cohesive`.

    References
    ----------
    Cites "Clean Code", Functions
    Cites "A Philosophy of Software Design", different layer different abstraction
    Cites "Refactoring", Extract Function
    """
    return backend.classification(
        subject,
        category=AbstractionLevel,
        instructions=abstraction_level.instructions,
    ).where(
        (pl.col("direct_statement_count") >= 6)
        & (pl.col("behavior_operation_count") >= 4)
        & ~pl.col("is_test"),
        requires=("direct_statement_count", "behavior_operation_count", "is_test"),
    )
