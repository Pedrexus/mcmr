from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import DependencyCandidateFact


class DependencyDecision(StrEnum):
    ADOPT = auto()
    WRAP = auto()
    WORK_AROUND = auto()
    BUILD = auto()
    FORK = auto()
    REPLACE = auto()
    UNCERTAIN = auto()


@rule
async def dependency_decision(
    subject: DependencyCandidateFact,
    backend: ClassificationBackend,
) -> DependencyDecision:
    """Recommend how to obtain and own one capability.

    Definition
    ----------
    Compare fit, maintenance, security, license, integration cost, alternatives, workarounds,
    fork effort, and long-term ownership. Missing load-bearing evidence requires abstention.

    Evidence
    --------
    Findings cite candidate facts, estimates, constraints, and rejected alternatives.

    Exceptions
    ----------
    Organizational mandates and regulated procurement can constrain the available category.

    Examples
    --------
    A maintained library matching the need is `adopt`. A nearly suitable abandoned library needing
    one small patch, with somebody ready to own it, is `fork`. A capability with no candidate at
    all is `build`, and a candidate whose maintenance evidence is missing is `uncertain`.

    References
    ----------
    Cites "The Pragmatic Programmer", on orthogonality and tracer bullets
    Cites "Google Engineering Practices", dependency guidance
    """
    return await backend.classify(
        subject,
        category=DependencyDecision,
        instructions=(
            "Compare fit, maintenance, security, license, integration cost, alternatives,"
            "workarounds, fork effort, and long-term ownership. Missing load-bearing"
            "evidence requires abstention."
        ),
    )
