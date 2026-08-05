from abc import ABC, abstractmethod
from enum import StrEnum
from typing import TYPE_CHECKING

from patos import FrozenModel

from .verdict import Verdict

if TYPE_CHECKING:
    from ...contracts import RuleValue

_REPORTED = {
    Verdict.PASS: "reports nothing and records the subject as acceptable",
    Verdict.FAIL: "reports the subject as a defect for someone to fix",
    Verdict.UNASSESSED: "reports nothing and leaves the subject unjudged",
}


class Policy(FrozenModel, ABC):
    """Decide whether one rule value is acceptable to this project."""

    def reported[Outcome: StrEnum](self, categories: type[Outcome]) -> dict[str, str]:
        """State what this project reports for each category, or nothing when it judges none.

        categories: the closed answer set a contextual rule offers a model.
        """
        stated = {str(item): self.verdict(str(item)) for item in categories}
        if all(verdict is Verdict.UNASSESSED for verdict in stated.values()):
            return {}
        return {name: _REPORTED[verdict] for name, verdict in stated.items()}

    @abstractmethod
    def verdict(self, value: RuleValue) -> Verdict:
        """Return the verdict this policy reaches for one observed value."""
