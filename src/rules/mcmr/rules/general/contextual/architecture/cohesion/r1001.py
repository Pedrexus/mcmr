from enum import StrEnum, auto

import polars as pl
from pydantic import PositiveInt

from ...... import Category, rule
from ......execution import ClassificationBackend
from ......execution.queries import ModelQuery
from ......facts import ModuleFact
from ......table import Table


class ModuleCohesion(StrEnum):
    """Name whether one module holds one responsibility or a deliberate integration role."""

    COHESIVE = auto()
    MIXED = auto()
    INTENTIONAL_INTEGRATION = auto()
    UNCERTAIN = auto()


@rule(
    "ALL-ARCH1001",
    policy=Category.outcomes(
        ModuleCohesion,
        good={ModuleCohesion.COHESIVE, ModuleCohesion.INTENTIONAL_INTEGRATION},
        neutral={ModuleCohesion.UNCERTAIN},
    ),
)
def module_cohesion(
    subject: Table[ModuleFact],
    backend: ClassificationBackend,
    *,
    minimum_members: PositiveInt = 4,
) -> ModelQuery[ModuleCohesion]:
    """Assess whether a module mixes unrelated responsibilities.

    Definition
    ----------
    Compare the exact source of every top-level declaration in one module. Mark it `mixed` only
    when at least two declarations implement unrelated domain outcomes. Mark an explicit facade,
    adapter, registry, or composition root `intentional_integration`. Otherwise keep a single
    responsibility as `cohesive` and missing semantic evidence as `uncertain`. `minimum_members`
    keeps very small modules out of this semantic pass.

    Evidence
    --------
    Findings retain the model reasoning and the exact declaration records it cited.

    Exceptions
    ----------
    Composition roots, facades, adapters, and deliberate integration modules may coordinate
    several systems while retaining one architectural responsibility. A smaller module remains
    excluded unless `minimum_members` is lowered.

    Examples
    --------
    Parsing invoices and sending unrelated email campaigns in one module is `mixed`. A composition
    root wiring both systems is `intentional_integration`.

    References
    ----------
    Cites "Clean Architecture", chapters 7 and 10
    Cites "Agile Software Development", chapter 8
    Cites "A Philosophy of Software Design", chapter 10
    """
    return backend.classification(
        subject,
        category=ModuleCohesion,
        instructions=module_cohesion.instructions,
    ).where(
        pl.col("members.length") >= minimum_members,
        requires=("members.length",),
    )
