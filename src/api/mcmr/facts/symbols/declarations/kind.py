from enum import StrEnum, auto


class ParameterKind(StrEnum):
    """Name how one parameter binds a caller's argument."""

    POSITIONAL_ONLY = auto()
    POSITIONAL_OR_KEYWORD = auto()
    KEYWORD_ONLY = auto()
    VAR_POSITIONAL = auto()
    VAR_KEYWORD = auto()
