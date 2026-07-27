from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import DependencyCandidateFact


class ThirdPartyAlternative(StrEnum):
    REUSE = auto()
    WRAP = auto()
    FORK = auto()
    BUILD = auto()
    UNCERTAIN = auto()


@rule
async def third_party_alternative(
    subject: DependencyCandidateFact,
    backend: ClassificationBackend,
) -> ThirdPartyAlternative:
    """Check whether maintained third-party code should replace custom work.

    Definition
    ----------
    Evaluate a documented search over package indexes, source hosts, and the standard
    library before recommending reuse, wrapping, forking, or building.

    Evidence
    --------
    Findings cite queries, candidates, maintenance signals, fit gaps, and ownership cost.

    Exceptions
    ----------
    Security, license, deployment, latency, and dependency-budget constraints may favor ownership.

    Examples
    --------
    A custom retry loop with a maintained retry package available is `reuse`. A ten-line domain
    calculation no package matches is `build`. A candidate that fits behind an adapter this project
    owns is `wrap`.

    References
    ----------
    Cites "The Pragmatic Programmer", DRY principle
    Cites "The Python Standard Library"
    Cites "OpenSSF Scorecard"
    """
    return await backend.classify(
        subject,
        category=ThirdPartyAlternative,
        instructions=(
            "Evaluate a documented search over package indexes, source hosts, and the"
            "standard library before recommending reuse, wrapping, forking, or building."
        ),
    )
