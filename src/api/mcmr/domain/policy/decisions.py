from enum import StrEnum
from typing import TYPE_CHECKING, Literal, Self

from pydantic import model_validator

from .contracts import Policy, Verdict
from .kinds import PolicyKind

if TYPE_CHECKING:
    from collections.abc import Iterable

    from ..contracts import RuleValue


class _PolicyDecisions:
    """Own the closed acceptance policies available to rule definitions."""

    class Boolean(Policy):
        """Require one exact Boolean value."""

        kind: Literal[PolicyKind.BOOLEAN] = PolicyKind.BOOLEAN
        expected: bool = False

        def verdict(self, value: RuleValue) -> Verdict:
            """Return whether the occurrence matched the expected Boolean."""
            if not isinstance(value, bool):
                return Verdict.UNASSESSED
            return Verdict.PASS if value is self.expected else Verdict.FAIL

    class Category(Policy):
        """Map every meaningful category to a good, neutral, or bad outcome."""

        kind: Literal[PolicyKind.CATEGORY] = PolicyKind.CATEGORY
        good: set[str] = set()
        neutral: set[str] = set()
        bad: set[str] = set()

        @classmethod
        def outcomes[Outcome: StrEnum](
            cls,
            categories: type[Outcome],
            *,
            good: Iterable[Outcome] = (),
            neutral: Iterable[Outcome] = (),
        ) -> Self:
            """Build a complete outcome map where every unstated category is bad."""
            universe = {str(item) for item in categories}
            accepted = {str(item) for item in good}
            undecided = {str(item) for item in neutral}
            return cls(good=accepted, neutral=undecided, bad=universe - accepted - undecided)

        @model_validator(mode="after")
        def partition(self) -> Self:
            """Require one nonempty partition with no category assigned twice."""
            buckets = [self.good, self.neutral, self.bad]
            if not any(buckets):
                raise ValueError("a category policy needs at least one category")
            if sum(map(len, buckets)) != len(self.good | self.neutral | self.bad):
                raise ValueError("good, neutral, and bad categories must be disjoint")
            return self

        def verdict(self, value: RuleValue) -> Verdict:
            """Return the declared outcome for one category."""
            if not isinstance(value, str):
                return Verdict.UNASSESSED
            if value in self.good:
                return Verdict.PASS
            if value in self.bad:
                return Verdict.FAIL
            return Verdict.UNASSESSED

    class Numeric(Policy):
        """Require a numeric value inside one closed interval."""

        kind: Literal[PolicyKind.NUMERIC] = PolicyKind.NUMERIC
        minimum: float | None = None
        maximum: float | None = None

        @model_validator(mode="after")
        def ordered(self) -> Self:
            """Reject an interval whose lower bound exceeds its upper bound."""
            if (
                self.minimum is not None
                and self.maximum is not None
                and self.minimum > self.maximum
            ):
                raise ValueError("minimum cannot exceed maximum")
            return self

        def verdict(self, value: RuleValue) -> Verdict:
            """Return whether one measurement falls inside the interval."""
            if isinstance(value, str | bool):
                return Verdict.UNASSESSED
            below = self.minimum is not None and value < self.minimum
            above = self.maximum is not None and value > self.maximum
            return Verdict.FAIL if below or above else Verdict.PASS


Boolean = _PolicyDecisions.Boolean
Category = _PolicyDecisions.Category
Numeric = _PolicyDecisions.Numeric
