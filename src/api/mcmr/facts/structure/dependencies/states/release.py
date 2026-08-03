from enum import StrEnum, auto


class DependencyReleaseState(StrEnum):
    """Name whether exact release yanking evidence is known and adverse."""

    UNKNOWN = auto()
    AVAILABLE = auto()
    YANKED = auto()
