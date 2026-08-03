from enum import StrEnum, auto

from ...... import Category, rule
from ......domain.contracts import Criterion
from ......execution import ClassificationBackend, CriterionValue
from ......execution.queries import AssessmentContract, ModelQuery
from ......facts import DeploymentFact
from ......table import Table


class _RolloutSuccessCriteria(StrEnum):
    DECISIVE = auto()
    INCOMPLETE = auto()
    MISALIGNED = auto()
    ABSENT = auto()
    UNCERTAIN = auto()


_CRITERIA = (
    Criterion(
        name="criteria exist", question="Are rollout success criteria stated before exposure?"
    ),
    Criterion(
        name="signals align with risks", question="Do attributable signals cover the stated risks?"
    ),
    Criterion(
        name="comparison is explicit", question="Are baselines and decision thresholds explicit?"
    ),
    Criterion(
        name="decision window is complete",
        question="Are windows, samples, missing data, and actions defined?",
    ),
)
_TABLE = (
    (_RolloutSuccessCriteria.ABSENT, (("criteria exist", CriterionValue.NO),)),
    (
        _RolloutSuccessCriteria.MISALIGNED,
        (("criteria exist", CriterionValue.YES), ("signals align with risks", CriterionValue.NO)),
    ),
    (
        _RolloutSuccessCriteria.DECISIVE,
        [(criterion.name, CriterionValue.YES) for criterion in _CRITERIA],
    ),
)


@rule(
    "ALL-DEPL1003",
    policy=Category.outcomes(
        _RolloutSuccessCriteria,
        good={_RolloutSuccessCriteria.DECISIVE},
        neutral={_RolloutSuccessCriteria.UNCERTAIN},
    ),
)
def rollout_success_criteria(
    subject: Table[DeploymentFact],
    backend: ClassificationBackend,
) -> ModelQuery[_RolloutSuccessCriteria]:
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
    return backend.assessment(
        subject,
        contract=AssessmentContract(
            criteria=list(_CRITERIA),
            instructions=rollout_success_criteria.instructions,
            decision_table=_TABLE,
            default=_RolloutSuccessCriteria.INCOMPLETE,
            uncertain=_RolloutSuccessCriteria.UNCERTAIN,
        ),
    )
