from enum import StrEnum, auto


class Placement(StrEnum):
    """Identify which side of an anchor receives a moved or inserted node."""

    BEFORE = auto()
    AFTER = auto()
