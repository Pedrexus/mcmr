from enum import StrEnum, auto

from ..... import rule
from .....backends import ClassificationBackend
from .....facts import DeploymentFact


class RolloutSuccessCriteria(StrEnum):
    DECISIVE = auto()
    INCOMPLETE = auto()
    MISALIGNED = auto()
    ABSENT = auto()
    UNCERTAIN = auto()


@rule
async def rollout_success_criteria(
    subject: DeploymentFact,
    backend: ClassificationBackend,
) -> RolloutSuccessCriteria:
    """Judge whether rollout success criteria support a clear decision.

    Definition
    ----------
    Ask the selected judgment backend for four independently cited criterion facts and reduce them
    through a fixed decision table. Compare stated risks with attributable signals, baselines,
    thresholds, observation windows, minimum samples, missing-data treatment, and decision actions.

    Evidence
    --------
    The frozen bundle cites risks, signals, comparisons, thresholds, windows, samples, and actions.
    Missing, duplicate, conflicting, or uncited answers remain `unknown` and reduce to `uncertain`.

    Exceptions
    ----------
    Deterministic offline validation may replace runtime criteria when it covers the full risk.

    Examples
    --------
    Error and latency bounds compared with a control over a minimum sample are `decisive`. A green
    deployment job without user-impact criteria is `absent`.

    References
    ----------
    Cites "The Site Reliability Workbook", Canarying Releases
    Cites "The Site Reliability Workbook", Alerting on SLOs
    Cites "Accelerate", continuous delivery
    """
    return await backend.classify(
        subject,
        category=RolloutSuccessCriteria,
        instructions=(
            "Ask the selected judgment backend for four independently cited criterion"
            "facts and reduce them through a fixed decision table. Compare stated risks"
            "with attributable signals, baselines, thresholds, observation windows,"
            "minimum samples, missing-data treatment, and decision actions."
        ),
    )
