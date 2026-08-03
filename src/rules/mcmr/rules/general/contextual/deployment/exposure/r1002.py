from enum import StrEnum, auto

from ...... import Category, rule
from ......domain.contracts import Criterion
from ......execution import ClassificationBackend, CriterionValue
from ......execution.queries import AssessmentContract, ModelQuery
from ......facts import DeploymentFact
from ......table import Table


class _ExposureControl(StrEnum):
    CONTROLLED = auto()
    PARTIAL = auto()
    UNBOUNDED = auto()
    NOT_REQUIRED = auto()
    UNCERTAIN = auto()


_CRITERIA = (
    Criterion(
        name="runtime controls required", question="Does this artifact expose runtime consumers?"
    ),
    Criterion(
        name="eligible population bounded",
        question="Is the eligible population explicit and bounded?",
    ),
    Criterion(
        name="traffic limit enforced", question="Does routing enforce a traffic or tenant limit?"
    ),
    Criterion(name="exposure time bounded", question="Is the exposure window explicitly bounded?"),
    Criterion(name="owner has authority", question="Can a named owner change or stop exposure?"),
    Criterion(name="halt works", question="Is there a working halt capability?"),
)
_TABLE = (
    (_ExposureControl.NOT_REQUIRED, (("runtime controls required", CriterionValue.NO),)),
    (_ExposureControl.UNBOUNDED, (("eligible population bounded", CriterionValue.NO),)),
    (_ExposureControl.UNBOUNDED, (("traffic limit enforced", CriterionValue.NO),)),
    (_ExposureControl.UNBOUNDED, (("halt works", CriterionValue.NO),)),
    (
        _ExposureControl.CONTROLLED,
        [(criterion.name, CriterionValue.YES) for criterion in _CRITERIA],
    ),
)


@rule(
    "ALL-DEPL1002",
    policy=Category.outcomes(
        _ExposureControl,
        good={_ExposureControl.CONTROLLED, _ExposureControl.NOT_REQUIRED},
        neutral={_ExposureControl.UNCERTAIN},
    ),
)
def exposure_control(
    subject: Table[DeploymentFact],
    backend: ClassificationBackend,
) -> ModelQuery[_ExposureControl]:
    """Judge whether deployment exposure is explicitly bounded.

    Definition
    ----------
    Ask the selected judgment backend for six independently cited exposure facts and reduce them
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
    return backend.assessment(
        subject,
        contract=AssessmentContract(
            criteria=list(_CRITERIA),
            instructions=exposure_control.instructions,
            decision_table=_TABLE,
            default=_ExposureControl.PARTIAL,
            uncertain=_ExposureControl.UNCERTAIN,
        ),
    )
