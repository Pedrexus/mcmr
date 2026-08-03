from enum import StrEnum, auto


class ReceiverKind(StrEnum):
    """Name whose member one access reads, relative to the accessing scope."""

    SELF = auto()
    OWNER = auto()
    SUPER = auto()
    OTHER = auto()
