from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import DeploymentFact


class ProgressiveRollout(StrEnum):
    VERIFIED = auto()
    PARTIAL = auto()
    UNSAFE = auto()
    NOT_NEEDED = auto()
    UNCERTAIN = auto()


@rule
async def progressive_rollout(
    subject: DeploymentFact,
    backend: ClassificationBackend,
) -> ProgressiveRollout:
    """Judge whether a risky deployment verifies behavior before broad exposure.

    Definition
    ----------
    Ask the selected judgment backend for five independently cited rollout facts and reduce them
    through a fixed decision table. The model never chooses the final category. Compare change
    exposure, stage representativeness, attributable outcomes, decision thresholds, and recovery.

    Evidence
    --------
    The frozen bundle cites rollout configuration, populations, signals, comparisons, thresholds,
    observation windows, and recovery actions. Missing, duplicate, conflicting, or uncited model
    answers remain `unknown` and reduce to `uncertain`.

    Exceptions
    ----------
    Low-risk offline artifacts may not need progressive exposure when equivalent verification
    covers the complete risk.

    Examples
    --------
    A representative canary compared with a control and protected by rollback is `verified`.
    Sending traffic to an unrepresentative stage without recovery is `unsafe`.

    References
    ----------
    Cites "The Site Reliability Workbook", Canarying Releases
    Cites "Accelerate", continuous delivery
    Cites "Release It", stability patterns
    """
    return await backend.classify(
        subject,
        category=ProgressiveRollout,
        instructions=(
            "Ask the selected judgment backend for five independently cited rollout facts"
            "and reduce them through a fixed decision table. The model never chooses the"
            "final category. Compare change exposure, stage representativeness,"
            "attributable outcomes, decision thresholds, and recovery."
        ),
    )
