from typing import TYPE_CHECKING

from patos import FrozenModel

from ....domain.primitives import NonEmptyStr

if TYPE_CHECKING:
    from ....domain.contracts import ModelProvenance

type ExperimentAnswer = str | dict[str, str]


class ContextualTrialFields:
    """Group flat contextual trial fields by case and backend outcome."""

    class Case(FrozenModel):
        """Retain the selected profile, rule, case, and expected answer."""

        profile: NonEmptyStr
        rule: NonEmptyStr
        case: NonEmptyStr
        expected: ExperimentAnswer

    class Outcome(Case):
        """Retain actual answer, status, explanation, evidence, and provenance."""

        actual: ExperimentAnswer | None = None
        passed: bool = False
        error: str = ""
        reasoning: list[str] = []
        evidence_ids: list[str] = []
        provenance: ModelProvenance | None = None
