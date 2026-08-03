from enum import StrEnum, auto

from ...... import Category, rule
from ......domain.contracts import Criterion
from ......execution import ClassificationBackend, CriterionValue
from ......execution.queries import AssessmentContract, ModelQuery
from ......facts import DeploymentFact
from ......table import Table


class _ProgressiveRollout(StrEnum):
    VERIFIED = auto()
    PARTIAL = auto()
    UNSAFE = auto()
    NOT_NEEDED = auto()
    UNCERTAIN = auto()


_CRITERIA = (
    Criterion(
        name="progressive rollout needed", question="Does this change need staged exposure?"
    ),
    Criterion(
        name="exposure is staged", question="Is broad exposure preceded by a bounded stage?"
    ),
    Criterion(
        name="stage is representative", question="Does the stage represent the risk population?"
    ),
    Criterion(
        name="outcomes decide", question="Are attributable outcomes compared with thresholds?"
    ),
    Criterion(
        name="recovery works", question="Can the rollout halt or recover when thresholds fail?"
    ),
)
_TABLE = (
    (
        _ProgressiveRollout.NOT_NEEDED,
        (("progressive rollout needed", CriterionValue.NO),),
    ),
    (
        _ProgressiveRollout.UNSAFE,
        (
            ("progressive rollout needed", CriterionValue.YES),
            ("exposure is staged", CriterionValue.NO),
        ),
    ),
    (
        _ProgressiveRollout.UNSAFE,
        (
            ("progressive rollout needed", CriterionValue.YES),
            ("stage is representative", CriterionValue.NO),
        ),
    ),
    (
        _ProgressiveRollout.UNSAFE,
        (
            ("progressive rollout needed", CriterionValue.YES),
            ("recovery works", CriterionValue.NO),
        ),
    ),
    (
        _ProgressiveRollout.VERIFIED,
        [(criterion.name, CriterionValue.YES) for criterion in _CRITERIA],
    ),
)


@rule(
    "ALL-DEPL1001",
    policy=Category.outcomes(
        _ProgressiveRollout,
        good={_ProgressiveRollout.NOT_NEEDED, _ProgressiveRollout.VERIFIED},
        neutral={_ProgressiveRollout.UNCERTAIN},
    ),
)
def progressive_rollout(
    subject: Table[DeploymentFact],
    backend: ClassificationBackend,
) -> ModelQuery[_ProgressiveRollout]:
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
    return backend.assessment(
        subject,
        contract=AssessmentContract(
            criteria=list(_CRITERIA),
            instructions=progressive_rollout.instructions,
            decision_table=_TABLE,
            default=_ProgressiveRollout.PARTIAL,
            uncertain=_ProgressiveRollout.UNCERTAIN,
        ),
    )
