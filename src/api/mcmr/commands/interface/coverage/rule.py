from enum import StrEnum, auto


class RuleCoverage(StrEnum):
    """Choose whether a check tolerates selected rules that cannot execute."""

    AVAILABLE = auto()
    ALL = auto()
