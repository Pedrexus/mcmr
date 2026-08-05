from enum import StrEnum, auto


class Category(StrEnum):
    """Small closed rubric used to verify the isolated harness."""

    SUPPORTED = auto()
    UNCERTAIN = auto()
