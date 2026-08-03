from enum import StrEnum, auto


class ExecutionOverride(StrEnum):
    """Name one explicit command-line change to a configured execution mode."""

    UNCHANGED = auto()
    ENABLED = auto()
    DISABLED = auto()
