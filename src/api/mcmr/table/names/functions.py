from enum import StrEnum, auto


class FunctionRelation(StrEnum):
    """Name every normalized relation belonging to `FunctionFact`."""

    FUNCTIONS = auto()
    PARAMETERS = auto()
    CONTROLS = auto()
    DECORATORS = auto()
    REFERENCES = auto()
    TENSOR_ROLES = auto()
    EVIDENCE = auto()
