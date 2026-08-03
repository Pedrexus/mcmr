from enum import StrEnum, auto


class MemberKind(StrEnum):
    """Name what one declared type member is in terms every object language shares."""

    CONSTRUCTOR = auto()
    DESTRUCTOR = auto()
    PROPERTY = auto()
    STATIC_METHOD = auto()
    CLASS_METHOD = auto()
    METHOD = auto()
    FIELD = auto()
