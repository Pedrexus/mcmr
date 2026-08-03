from enum import StrEnum, auto


class MemberKind(StrEnum):
    """Say which UML compartment one member belongs in."""

    ATTRIBUTE = auto()
    METHOD = auto()
