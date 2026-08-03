from enum import StrEnum, auto


class GenericRelation(StrEnum):
    """Name the universal relations of each schema-normalized fact family."""

    FACTS = auto()
    RECORDS = auto()
    VALUES = auto()
