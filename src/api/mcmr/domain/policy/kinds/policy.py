from enum import StrEnum, auto


class PolicyKind(StrEnum):
    """Identify which typed policy decides one observation."""

    NUMERIC = auto()
    BOOLEAN = auto()
    CATEGORY = auto()
