from enum import StrEnum, auto


class Coverage(StrEnum):
    """Classify how completely MCMR answers an upstream rule."""

    NATIVE = auto()
    DELEGATED = auto()
    ADAPTED = auto()
    INAPPLICABLE = auto()
    UNAVAILABLE = auto()
