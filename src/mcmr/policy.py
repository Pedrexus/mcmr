from abc import ABC, abstractmethod
from enum import StrEnum, auto
from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import Field

from .bases import FrozenFlexModel

if TYPE_CHECKING:
    from .models import RuleDefinition, RuleValue


class Verdict(StrEnum):
    """Say whether one observation met the policy a project selected for it."""

    PASS = auto()
    FAIL = auto()
    UNASSESSED = auto()


class PolicyKind(StrEnum):
    """Identify which typed policy decides one observation."""

    NUMERIC = auto()
    BOOLEAN = auto()
    CATEGORY = auto()


class Policy(FrozenFlexModel, ABC):
    """Decide whether one rule value is acceptable to this project."""

    @abstractmethod
    def verdict(self, value: RuleValue) -> Verdict:
        """Return the verdict this policy reaches for one observed value."""


class Numeric(Policy):
    """Require a numeric value inside one closed interval.

    A measurement carries no verdict of its own. Module length, complexity, and nesting depth are
    facts about a codebase, and only a project can say which magnitude it is willing to live with,
    which is why a rule that measures stays unassessed until a profile states the interval.
    """

    kind: Literal[PolicyKind.NUMERIC] = PolicyKind.NUMERIC
    minimum: float | None = None
    maximum: float | None = None

    def verdict(self, value: RuleValue) -> Verdict:
        """Return whether one measurement falls inside the interval."""
        if isinstance(value, str | bool):
            return Verdict.UNASSESSED
        below = self.minimum is not None and value < self.minimum
        above = self.maximum is not None and value > self.maximum
        return Verdict.FAIL if below or above else Verdict.PASS


class Boolean(Policy):
    """Require one exact Boolean value, which is false for an occurrence by default."""

    kind: Literal[PolicyKind.BOOLEAN] = PolicyKind.BOOLEAN
    expected: bool = False

    def verdict(self, value: RuleValue) -> Verdict:
        """Return whether the occurrence matched what the project expects."""
        if not isinstance(value, bool):
            return Verdict.UNASSESSED
        return Verdict.PASS if value is self.expected else Verdict.FAIL


class Category(Policy):
    """Accept one nonempty set of categories and reject the rest."""

    kind: Literal[PolicyKind.CATEGORY] = PolicyKind.CATEGORY
    accepted: frozenset[str] = Field(min_length=1)

    def verdict(self, value: RuleValue) -> Verdict:
        """Return whether the category is one this project accepts."""
        if not isinstance(value, str):
            return Verdict.UNASSESSED
        return Verdict.PASS if value in self.accepted else Verdict.FAIL


type RulePolicy = Annotated[Numeric | Boolean | Category, Field(discriminator="kind")]


class Profile(FrozenFlexModel):
    """Hold one named strictness level and the policies it applies.

    Strictness is a project decision, not a property of a rule. A profile states a default for each
    result shape and then overrides the rules whose acceptable magnitude differs from counting
    findings, so a project moves between levels by naming one instead of restating every threshold.
    """

    name: str
    occurrences: RulePolicy = Boolean()
    counts: RulePolicy | None = None
    percentages: RulePolicy | None = None
    categories: RulePolicy | None = None
    overrides: dict[str, RulePolicy] = {}

    def policy(self, definition: RuleDefinition) -> Policy | None:
        """Return the policy this profile applies to one rule, if it states any."""
        if override := self.overrides.get(definition.id):
            return override
        match definition.output, definition.unit:
            case "bool", _:
                return self.occurrences
            case "int", _:
                return self.counts
            case "float", _:
                return self.percentages
            case "category", _:
                return self.categories
            case _:
                return None

    def decide(self, definition: RuleDefinition, value: RuleValue) -> Verdict:
        """Return the verdict for one observation under this profile."""
        policy = self.policy(definition)
        return policy.verdict(value) if policy else Verdict.UNASSESSED


def relaxed() -> Profile:
    """Return the profile that only reports what a rule states as an occurrence.

    Nothing here is a matter of taste. An occurrence rule names a specific defect, so its default
    expectation is that the defect is absent, while every magnitude stays unassessed until a
    project decides what it will accept.
    """
    return Profile(name="relaxed")


def standard() -> Profile:
    """Return the profile most projects should start from.

    A count is a count of findings unless the rule measures something, so the default maximum is
    zero and the measuring rules carry the intervals that make them meaningful. The numbers here
    are deliberately ordinary: they are the sizes at which a reader starts holding too much in
    mind, not the sizes at which code stops working.

    A percentage needs its direction stated. Coverage is judged by a floor, while a density or a
    concentration is judged by a ceiling, and only the rule knows which it reports, so each
    density rule carries its own override.
    """
    return Profile(
        name="standard",
        counts=Numeric(maximum=0),
        percentages=Numeric(minimum=80.0),
        overrides={
            "ALL-MODU0001": Numeric(maximum=500),
            "ALL-MODU0002": Numeric(maximum=20),
            "ALL-FUNC0001": Numeric(maximum=50),
            "ALL-FUNC0011": Numeric(maximum=8),
            "ALL-FUNC0012": Numeric(maximum=15),
            "ALL-FUNC0013": Numeric(maximum=4),
            "ALL-FUNC0014": Numeric(maximum=5),
            "ALL-FILE0002": Numeric(maximum=5),
            "ALL-FILE0003": Numeric(maximum=20),
            "ALL-COMM0002": Numeric(maximum=40),
            # Each of these takes the upstream tool's own default, so a project moving from Pylint
            # or Clippy meets the bar it already met. The field count sits above Pylint's seven
            # because it counts declared state as well as what a receiver assigns.
            "ALL-CLAS0007": Numeric(maximum=20),
            "ALL-CLAS0008": Numeric(maximum=12),
            "ALL-CLAS0009": Numeric(maximum=7),
            "ALL-PARA0004": Numeric(maximum=3),
            "PY-COMP0002": Numeric(maximum=2),
            "PY-TEST0020": Numeric(maximum=15),
            "PY-TEST0019": Numeric(maximum=2),
            "ALL-WRIT0003": Numeric(maximum=90.0),
            "ALL-WRIT0004": Numeric(maximum=90.0),
            "ALL-WRIT0005": Numeric(maximum=40.0),
            # A duplicated share is a density, so it is judged by a ceiling like every other one.
            # Five percent is the figure the industry has settled on, and a project below it is
            # duplicating deliberately rather than by accident.
            "ALL-DUPL0004": Numeric(maximum=5.0),
            "TS-MODU0002": Numeric(maximum=2),
            "TS-TYPE0001": Numeric(maximum=0),
            "TS-TYPE0002": Numeric(maximum=5.0),
            # Borrowing and copying are the two halves of one trade, so both carry a ceiling
            # rather than a prohibition. A project holding zero of either has usually paid for it
            # in the other.
            "RS-LIFE0003": Numeric(maximum=4),
            "RS-OWNE0001": Numeric(maximum=4),
            "RS-OWNE0002": Numeric(maximum=20),
        },
    )


def strict() -> Profile:
    """Return the profile for a codebase that intends to stay small and readable.

    This is the opinionated one, and it is meant to be. It keeps the same shape as the standard
    profile and tightens every magnitude a project can reasonably hold itself to.
    """
    base = standard()
    return base.model_copy(
        update={
            "name": "strict",
            "percentages": Numeric(minimum=95.0),
            "overrides": base.overrides
            | {
                "ALL-MODU0001": Numeric(maximum=300),
                "ALL-MODU0002": Numeric(maximum=12),
                "ALL-FUNC0001": Numeric(maximum=30),
                "ALL-FUNC0011": Numeric(maximum=4),
                "ALL-FUNC0012": Numeric(maximum=8),
                "ALL-FUNC0013": Numeric(maximum=2),
                "ALL-FUNC0014": Numeric(maximum=4),
                "ALL-COMM0002": Numeric(maximum=20),
                "ALL-CLAS0007": Numeric(maximum=10),
                "ALL-CLAS0008": Numeric(maximum=7),
                "ALL-CLAS0009": Numeric(maximum=5),
                "ALL-PARA0004": Numeric(maximum=1),
                "PY-TEST0020": Numeric(maximum=10),
                "ALL-WRIT0005": Numeric(maximum=30.0),
                "ALL-DUPL0004": Numeric(maximum=3.0),
                "TS-MODU0002": Numeric(maximum=1),
                "TS-TYPE0002": Numeric(maximum=2.0),
                "RS-LIFE0003": Numeric(maximum=2),
                "RS-OWNE0001": Numeric(maximum=1),
                "RS-OWNE0002": Numeric(maximum=10),
            },
        }
    )


def profiles() -> dict[str, Profile]:
    """Return every profile this release ships, by name."""
    return {profile.name: profile for profile in (relaxed(), standard(), strict())}
