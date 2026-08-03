from enum import StrEnum, auto


class ReplacementState(StrEnum):
    """State how one legacy capability leaves GE4M behind."""

    NATIVE = auto()
    DELEGATED = auto()
    RETIRED = auto()
    MISSING = auto()
