from enum import StrEnum, auto


class SourceKind(StrEnum):
    """Say what kind of source one rule leaned on."""

    BOOK = auto()
    PAPER = auto()
    STANDARD = auto()
    LANGUAGE = auto()
    DOCUMENTATION = auto()
    ARTICLE = auto()
    TOOL = auto()
