from enum import StrEnum, auto

import polars as pl

from ..... import Category, rule
from .....execution import ClassificationBackend
from .....execution.queries import ModelQuery
from .....facts import ClassFact
from .....table import Table


class _DesignPatternFit(StrEnum):
    USEFUL = auto()
    MISSING = auto()
    PREMATURE = auto()
    MISAPPLIED = auto()
    NOT_NEEDED = auto()
    UNCERTAIN = auto()


@rule(
    "ALL-DESI1002",
    policy=Category.outcomes(
        _DesignPatternFit,
        good={_DesignPatternFit.NOT_NEEDED, _DesignPatternFit.USEFUL},
        neutral={_DesignPatternFit.UNCERTAIN},
    ),
)
def design_pattern_fit(
    subject: Table[ClassFact],
    backend: ClassificationBackend,
) -> ModelQuery[_DesignPatternFit]:
    """Judge whether a design pattern earns its structure.

    Definition
    ----------
    Compare current variation, change pressure, collaboration, ownership, alternatives,
    and added indirection with the forces of the proposed or existing pattern. The criteria
    independently establish recurring variation, existing structure, matched forces, reduced
    change coupling, and whether direct code is clearer.

    Evidence
    --------
    Findings cite variants, change sites, collaborators, tests, and simpler alternatives.

    Exceptions
    ----------
    Framework contracts may impose a pattern even when project variation is small.

    Examples
    --------
    Strategy fits several interchangeable pricing algorithms. A factory around one direct
    constructor with no variation is likely `premature`.

    References
    ----------
    Cites "Design Patterns"
    Cites "Refactoring Guru", design patterns
    Cites "patos documentation", pattern contracts
    """
    return backend.classification(
        subject,
        category=_DesignPatternFit,
        instructions=design_pattern_fit.instructions,
    ).where(
        (pl.col("methods.length") >= 2) & pl.col("has_instance_fields") & ~pl.col("is_test"),
        requires=("methods.length", "has_instance_fields", "is_test"),
    )
