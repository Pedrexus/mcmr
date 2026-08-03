from enum import StrEnum

from patos import FrozenModel
from pydantic import field_validator

from ....domain.contracts import Criterion
from ..definitions import DecisionTable


class AssessmentContract[Category: StrEnum](FrozenModel):
    """Own one cited assessment rubric and its deterministic reduction."""

    criteria: list[Criterion]
    instructions: str
    decision_table: DecisionTable[Category]
    default: Category
    uncertain: Category

    @field_validator("criteria")
    @classmethod
    def unique_criteria(cls, criteria: list[Criterion]) -> list[Criterion]:
        """Require criterion names to be unambiguous within one rubric."""
        if not criteria:
            raise ValueError("a model assessment needs at least one criterion")
        names = [criterion.name for criterion in criteria]
        if len(names) != len(set(names)):
            raise ValueError("model assessment criterion names must be unique")
        return criteria
