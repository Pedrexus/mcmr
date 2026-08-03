from enum import StrEnum, auto

from ...... import Category, rule
from ......domain.contracts import Criterion
from ......execution import ClassificationBackend, CriterionValue
from ......execution.queries import AssessmentContract, ModelQuery
from ......facts import DeploymentFact
from ......table import Table


class _RollbackReadiness(StrEnum):
    READY = auto()
    PARTIAL = auto()
    UNVERIFIED = auto()
    BLOCKED = auto()
    NOT_REQUIRED = auto()
    UNCERTAIN = auto()


_CRITERIA = (
    Criterion(
        name="rollback required",
        question="Does the change have a deployed effect that may need reversal?",
    ),
    Criterion(
        name="artifacts and state compatible",
        question="Can old artifacts read the resulting state safely?",
    ),
    Criterion(
        name="steps are owned and timely",
        question="Are executable steps, timing, and owner authority established?",
    ),
    Criterion(
        name="representative rehearsal passed",
        question="Has the rollback run under representative conditions?",
    ),
    Criterion(
        name="material blockers absent",
        question="Are there no material blockers to completing rollback?",
    ),
)
_TABLE = (
    (_RollbackReadiness.NOT_REQUIRED, (("rollback required", CriterionValue.NO),)),
    (_RollbackReadiness.BLOCKED, (("artifacts and state compatible", CriterionValue.NO),)),
    (_RollbackReadiness.BLOCKED, (("material blockers absent", CriterionValue.NO),)),
    (
        _RollbackReadiness.READY,
        [(criterion.name, CriterionValue.YES) for criterion in _CRITERIA],
    ),
    (
        _RollbackReadiness.UNVERIFIED,
        (
            ("rollback required", CriterionValue.YES),
            ("artifacts and state compatible", CriterionValue.YES),
            ("steps are owned and timely", CriterionValue.YES),
            ("representative rehearsal passed", CriterionValue.NO),
            ("material blockers absent", CriterionValue.YES),
        ),
    ),
)


@rule(
    "ALL-DEPL1004",
    policy=Category.outcomes(
        _RollbackReadiness,
        good={_RollbackReadiness.NOT_REQUIRED, _RollbackReadiness.READY},
        neutral={_RollbackReadiness.UNCERTAIN},
    ),
)
def rollback_readiness(
    subject: Table[DeploymentFact],
    backend: ClassificationBackend,
) -> ModelQuery[_RollbackReadiness]:
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
    return backend.assessment(
        subject,
        contract=AssessmentContract(
            criteria=list(_CRITERIA),
            instructions=rollback_readiness.instructions,
            decision_table=_TABLE,
            default=_RollbackReadiness.PARTIAL,
            uncertain=_RollbackReadiness.UNCERTAIN,
        ),
    )
