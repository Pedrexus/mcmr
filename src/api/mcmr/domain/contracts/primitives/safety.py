from enum import StrEnum, auto


class FixSafety(StrEnum):
    """Describe how confidently MCMR may apply one fix."""

    SAFE = auto()
    REVIEW = auto()
