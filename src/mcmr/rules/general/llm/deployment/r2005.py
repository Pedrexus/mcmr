from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import DeploymentFact


class RollbackReadiness(StrEnum):
    READY = auto()
    PARTIAL = auto()
    UNVERIFIED = auto()
    BLOCKED = auto()
    NOT_REQUIRED = auto()
    UNCERTAIN = auto()


@rule
async def rollback_readiness(
    subject: DeploymentFact,
    backend: ClassificationBackend,
) -> RollbackReadiness:
    """Judge whether a deployment has a usable rollback path.

    Definition
    ----------
    Ask the selected judgment backend for five independently cited rollback facts and reduce them
    through a fixed decision table. Compare artifacts, state compatibility, steps, timing, owner
    authority, rehearsal evidence, and material blockers.

    Evidence
    --------
    The frozen bundle cites rollback artifacts, state, timing, owners, rehearsal runs, and
    blockers.
    Missing, duplicate, conflicting, or uncited answers remain `unknown` and reduce to `uncertain`.

    Exceptions
    ----------
    A change with no deployed effect can be `not_required`. An authorized one-way change needs a
    verified recovery path and should be assessed by the migration rules instead.

    Examples
    --------
    A compatible path with an owner and recent timed rehearsal is `ready`. A documented command
    that has never run under representative conditions is `unverified`.

    References
    ----------
    Cites "The Site Reliability Workbook", Canarying Releases
    Cites "Accelerate", continuous delivery
    Cites "Release It", stability patterns
    """
    return await backend.classify(
        subject,
        category=RollbackReadiness,
        instructions=(
            "Ask the selected judgment backend for five independently cited rollback"
            "facts and reduce them through a fixed decision table. Compare artifacts,"
            "state compatibility, steps, timing, owner authority, rehearsal evidence, and"
            "material blockers."
        ),
    )
