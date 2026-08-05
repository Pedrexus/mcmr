from enum import StrEnum, auto


class CertainCategory(StrEnum):
    """Closed rubric with no uncertainty answer."""

    SUPPORTED = auto()
