from enum import StrEnum, auto


class Verdict(StrEnum):
    """Say whether one observation met the policy a project selected for it."""

    PASS = auto()
    FAIL = auto()
    UNASSESSED = auto()
