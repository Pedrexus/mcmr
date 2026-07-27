from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import ArchitectureBoundaryFact


class DependencyBoundaryAlignment(StrEnum):
    ALIGNED = auto()
    LEAKY = auto()
    INTENTIONAL_BRIDGE = auto()
    UNCERTAIN = auto()


@rule
async def dependency_boundary_alignment(
    subject: ArchitectureBoundaryFact,
    backend: ClassificationBackend,
) -> DependencyBoundaryAlignment:
    """Judge whether dependencies honor one identified architectural boundary.

    Definition
    ----------
    Require evidence naming the intended boundary before judging it. Separately establish use
    of public entries, repeated internal bypasses, coordinated changes, and a deliberate bridge
    role. Missing intent produces uncertainty rather than a guessed architecture violation.

    Evidence
    --------
    Findings cite the compact graph nodes, declared boundary, consumers, and representative
    changes that establish or contradict the crossing.

    Exceptions
    ----------
    Adapters, facades, gateways, and composition roots may intentionally cross boundaries.

    Examples
    --------
    Three feature packages calling private storage implementation classes behind a repository
    interface are `leaky`. One HTTP adapter translating into that same interface is an
    `intentional_bridge`. Consumers reaching the storage package only through its public entries
    are `aligned`, and a boundary no evidence names at all is `uncertain`.

    References
    ----------
    Cites "Clean Architecture", boundary anatomy
    Cites "Domain-Driven Design", bounded contexts and anticorruption layers
    Cites "Building Evolutionary Architectures", dependency fitness functions
    """
    return await backend.classify(
        subject,
        category=DependencyBoundaryAlignment,
        instructions=(
            "Require evidence naming the intended boundary before judging it. Separately"
            "establish use of public entries, repeated internal bypasses, coordinated"
            "changes, and a deliberate bridge role. Missing intent produces uncertainty"
            "rather than a guessed architecture violation."
        ),
    )
