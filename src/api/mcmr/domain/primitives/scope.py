from enum import StrEnum, auto


class RuleScope(StrEnum):
    """Identify the language a rule answers for, or every language."""

    GENERAL = auto()
    PYTHON = auto()
    RUST = auto()
    TYPESCRIPT = auto()
    C = auto()
    CPP = auto()
    CUDA = auto()

    @property
    def prefix(self) -> str:
        """Return the identifier prefix rules in this scope carry."""
        match self:
            case RuleScope.GENERAL:
                return "ALL"
            case RuleScope.PYTHON:
                return "PY"
            case RuleScope.RUST:
                return "RS"
            case RuleScope.TYPESCRIPT:
                return "TS"
            case RuleScope.C:
                return "C"
            case RuleScope.CPP:
                return "CPP"
            case _:
                return "CU"
