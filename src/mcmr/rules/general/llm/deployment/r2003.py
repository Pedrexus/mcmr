from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import DeploymentFact


class ExposureControl(StrEnum):
    CONTROLLED = auto()
    PARTIAL = auto()
    UNBOUNDED = auto()
    NOT_REQUIRED = auto()
    UNCERTAIN = auto()


@rule
async def exposure_control(
    subject: DeploymentFact,
    backend: ClassificationBackend,
) -> ExposureControl:
    """Judge whether deployment exposure is explicitly bounded.

    Definition
    ----------
    Ask the selected judgment backend for five independently cited exposure facts and reduce them
    through a fixed decision table. Compare eligible populations, traffic or tenant limits, time
    bounds, routing enforcement, owner authority, and working halt capability.

    Evidence
    --------
    The frozen bundle cites rollout populations, routing configuration, limits, owners, windows,
    and stops. Missing, duplicate, conflicting, or uncited answers remain `unknown` and reduce to
    `uncertain`.

    Exceptions
    ----------
    Offline artifacts without runtime consumers may not require progressive exposure controls.

    Examples
    --------
    A tenant allowlist with a traffic cap, review time, owner, and tested halt is `controlled`. A
    nominal canary that can route all traffic is `unbounded`.

    References
    ----------
    Cites "The Site Reliability Workbook", Canarying Releases
    Cites "Release It", stability patterns
    Cites "Accelerate", continuous delivery
    """
    return await backend.classify(
        subject,
        category=ExposureControl,
        instructions=(
            "Ask the selected judgment backend for five independently cited exposure"
            "facts and reduce them through a fixed decision table. Compare eligible"
            "populations, traffic or tenant limits, time bounds, routing enforcement,"
            "owner authority, and working halt capability."
        ),
    )
