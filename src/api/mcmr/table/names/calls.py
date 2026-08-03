from enum import StrEnum, auto


class CallRelation(StrEnum):
    """Name every normalized relation belonging to `CallFact`."""

    FACTS = auto()
    CALLS = auto()
    KEYWORDS = auto()
    EXPRESSIONS = auto()
    EXPRESSION_ANCESTRY = auto()
    MAPPING_ENTRIES = auto()
    MODULE_BINDINGS = auto()
    EVIDENCE = auto()
