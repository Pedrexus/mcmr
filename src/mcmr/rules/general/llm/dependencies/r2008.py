from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import DependencyCandidateFact


class IntegrationEffort(StrEnum):
    LOW = auto()
    MODERATE = auto()
    HIGH = auto()
    PROHIBITIVE = auto()
    UNCERTAIN = auto()


@rule
async def integration_effort(
    subject: DependencyCandidateFact,
    backend: ClassificationBackend,
) -> IntegrationEffort:
    """Judge the integration effort for one dependency candidate.

    Definition
    ----------
    Compare API adaptation, data migration, configuration, deployment, observability, tests,
    training, lock-in, and removal cost while excluding long-term upstream maintenance outlook.

    Evidence
    --------
    Findings cite affected boundaries, adapters, migrations, operations, estimates, and unknowns.

    Exceptions
    ----------
    Existing organizational infrastructure may lower effort when concrete reusable support exists.

    Examples
    --------
    A typed adapter around a compatible client is `low` effort. Replacing persistence and
    deployment models across services is `high` effort even when the new library is capable.

    References
    ----------
    Cites "Patterns of Enterprise Application Architecture"
    Cites "Google Engineering Practices", dependency guidance
    Cites "Accelerate", deployment and change risk
    """
    return await backend.classify(
        subject,
        category=IntegrationEffort,
        instructions=(
            "Compare API adaptation, data migration, configuration, deployment,"
            "observability, tests, training, lock-in, and removal cost while excluding"
            "long-term upstream maintenance outlook."
        ),
    )
