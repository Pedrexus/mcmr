from typing import TYPE_CHECKING

from patos import FrozenModel
from pydantic import model_validator

from ...domain.primitives import NonEmptyStr
from ...execution import CriterionValue

if TYPE_CHECKING:
    from typing import Self


class ContextualExpectation(FrozenModel):
    """State the reviewed answer one contextual candidate must receive."""

    classification: NonEmptyStr | None = None
    criteria: dict[NonEmptyStr, CriterionValue] = {}

    @model_validator(mode="after")
    def one_mode(self) -> Self:
        """Require exactly one classification or predicate expectation."""
        if (self.classification is None) == (not self.criteria):
            raise ValueError("an expectation needs exactly one classification or criteria map")
        return self

    def rendered(self) -> str | dict[str, str]:
        """Return the stable JSON-shaped answer used in reports."""
        if self.classification is not None:
            return self.classification
        return {name: str(value) for name, value in self.criteria.items()}
