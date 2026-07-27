from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import DependencyCandidateFact


class ForkMaintainability(StrEnum):
    SUSTAINABLE = auto()
    CONDITIONAL = auto()
    UNSUSTAINABLE = auto()
    UNNECESSARY = auto()
    UNCERTAIN = auto()


@rule
async def fork_maintainability(
    subject: DependencyCandidateFact,
    backend: ClassificationBackend,
) -> ForkMaintainability:
    """Judge whether the project can maintain a dependency fork.

    Definition
    ----------
    Compare patch surface, expected divergence, upstream merge frequency, expertise, ownership,
    tests, packaging, security response, release operations, and exit strategy.

    Evidence
    --------
    Findings cite patches, upstream history, responsible engineers, budgets, pipelines, and exits.

    Exceptions
    ----------
    A frozen internal fork may be sustainable when its environment and threat surface are bounded.

    Examples
    --------
    A ten-line owned patch with automated upstream merging can be `sustainable`. Forking a security
    framework without domain expertise or release ownership is `unsustainable`.

    References
    ----------
    Cites "Google Engineering Practices", dependency guidance
    Cites "Open Source Project Security Baseline", maintaining critical software
    Cites "Producing Open Source Software"
    """
    return await backend.classify(
        subject,
        category=ForkMaintainability,
        instructions=(
            "Compare patch surface, expected divergence, upstream merge frequency,"
            "expertise, ownership, tests, packaging, security response, release"
            "operations, and exit strategy."
        ),
    )
