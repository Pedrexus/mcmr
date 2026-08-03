from enum import StrEnum, auto


class RelationKind(StrEnum):
    """Say what one line drawn between two boxes means."""

    INHERIT = auto()
    IMPORT = auto()
