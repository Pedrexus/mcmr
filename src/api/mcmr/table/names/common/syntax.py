from enum import StrEnum, auto


class SyntaxRelation(StrEnum):
    """Name every normalized relation belonging to `SyntaxFact`."""

    FACTS = auto()
    NODES = auto()
    CHILDREN = auto()
