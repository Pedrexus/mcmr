from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import DesignStructureFact


class DesignPatternFit(StrEnum):
    USEFUL = auto()
    MISSING = auto()
    PREMATURE = auto()
    MISAPPLIED = auto()
    NOT_NEEDED = auto()
    UNCERTAIN = auto()


@rule
async def design_pattern_fit(
    subject: DesignStructureFact,
    backend: ClassificationBackend,
) -> DesignPatternFit:
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
    return await backend.classify(
        subject,
        category=DesignPatternFit,
        instructions=(
            "Compare current variation, change pressure, collaboration, ownership,"
            "alternatives, and added indirection with the forces of the proposed or"
            "existing pattern. The criteria independently establish recurring variation,"
            "existing structure, matched forces, reduced change coupling, and whether"
            "direct code is clearer."
        ),
    )
