from enum import StrEnum, auto


class DependencyProjectState(StrEnum):
    """Name the publication state of one dependency project."""

    UNKNOWN = auto()
    ACTIVE = auto()
    ARCHIVED = auto()
    DEPRECATED = auto()
    QUARANTINED = auto()
