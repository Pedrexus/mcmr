from enum import StrEnum, auto


class DependencyRepositoryState(StrEnum):
    """Name whether repository archive evidence is known and adverse."""

    UNKNOWN = auto()
    ACTIVE = auto()
    ARCHIVED = auto()
