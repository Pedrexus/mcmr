from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import InterfaceFact


class InterfaceSegregation(StrEnum):
    FOCUSED = auto()
    BLOATED = auto()
    FRAGMENTED = auto()
    FACADE = auto()
    UNCERTAIN = auto()


@rule
async def interface_segregation(
    subject: InterfaceFact,
    backend: ClassificationBackend,
) -> InterfaceSegregation:
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
    return await backend.classify(
        subject,
        category=InterfaceSegregation,
        instructions=(
            "Compare interface members with the subsets used by each client and"
            "implemented meaningfully by each provider. Small size alone does not"
            "establish a focused interface. The criteria independently establish client"
            "usage, provider support, distinct subsets, split cost, and a facade"
            "boundary."
        ),
    )
