from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import DependencyHubFact


class DependencyHubQuality(StrEnum):
    STABLE_ABSTRACTION = auto()
    INTENTIONAL_COORDINATOR = auto()
    DEPENDENCY_MAGNET = auto()
    UNCERTAIN = auto()


@rule
async def dependency_hub_quality(
    subject: DependencyHubFact,
    backend: ClassificationBackend,
) -> DependencyHubQuality:
    """Judge the role of one deterministically nominated dependency hub.

    Definition
    ----------
    Apply only after graph metrics establish a comparable degree outlier. Judge contract
    cohesion, stability across representative changes, consumer-specific knowledge, and a
    deliberate coordination role independently. High degree alone is never a failure.

    Evidence
    --------
    Findings cite graph degrees, focused node relationships, public surface, consumers, and
    representative changes. Whole-repository orientation may locate the hub but cannot prove
    consumer-specific knowledge by itself.

    Exceptions
    ----------
    Stable abstractions, facades, application services, and composition roots are useful hubs.

    Examples
    --------
    A small repository protocol many services import is a `stable_abstraction`. A `Manager` class
    carrying unrelated consumer flags and a branch per caller is a `dependency_magnet`. An
    application service deliberately wiring several collaborators is an `intentional_coordinator`,
    and a hub with no evidence about consumer knowledge is `uncertain`.

    References
    ----------
    Cites "Clean Architecture", stable dependencies principle
    Cites "A Philosophy of Software Design", deep modules
    Cites "Agile Software Development", dependency inversion principle
    """
    return await backend.classify(
        subject,
        category=DependencyHubQuality,
        instructions=(
            "Apply only after graph metrics establish a comparable degree outlier. Judge"
            "contract cohesion, stability across representative changes,"
            "consumer-specific knowledge, and a deliberate coordination role"
            "independently. High degree alone is never a failure."
        ),
    )
