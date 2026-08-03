from enum import StrEnum, auto


class DiagramKind(StrEnum):
    """Name one view of the repository graph."""

    CLASS = auto()
    PACKAGE = auto()
