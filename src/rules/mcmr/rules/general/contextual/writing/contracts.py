from enum import StrEnum, auto


class ProseLanguage(StrEnum):
    """Classify whether source prose follows the configured project language."""

    TARGET = auto()
    OTHER = auto()
    UNCERTAIN = auto()
