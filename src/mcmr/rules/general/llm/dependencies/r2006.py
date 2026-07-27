from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import DependencyCandidateFact


class CapabilityFit(StrEnum):
    EXACT = auto()
    ADEQUATE = auto()
    UNDERFIT = auto()
    OVERFIT = auto()
    UNCERTAIN = auto()


@rule
async def capability_fit(
    subject: DependencyCandidateFact,
    backend: ClassificationBackend,
) -> CapabilityFit:
    """Judge whether one candidate fits the required capability.

    Definition
    ----------
    Compare required behavior, scale, environments, constraints, extension points, and unwanted
    surface without considering maintenance or integration effort.

    Evidence
    --------
    Findings cite explicit requirements, candidate guarantees, unsupported cases, and excess scope.

    Exceptions
    ----------
    A deliberate platform standard may accept bounded excess surface when the constraint is stated.

    Examples
    --------
    A retry library supporting required policies is `exact`. A workflow engine used only for three
    retries is `overfit`. A client lacking required cancellation is `underfit`.

    References
    ----------
    Cites "Google Engineering Practices", dependency guidance
    Cites "The Pragmatic Programmer", on orthogonality
    Cites "A Philosophy of Software Design", deep modules
    """
    return await backend.classify(
        subject,
        category=CapabilityFit,
        instructions=(
            "Compare required behavior, scale, environments, constraints, extension"
            "points, and unwanted surface without considering maintenance or integration"
            "effort."
        ),
    )
