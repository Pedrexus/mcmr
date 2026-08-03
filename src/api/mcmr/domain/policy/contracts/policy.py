from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from patos import FrozenModel

if TYPE_CHECKING:
    from ...contracts import RuleValue
    from .verdict import Verdict


class Policy(FrozenModel, ABC):
    """Decide whether one rule value is acceptable to this project."""

    @abstractmethod
    def verdict(self, value: RuleValue) -> Verdict:
        """Return the verdict this policy reaches for one observed value."""
