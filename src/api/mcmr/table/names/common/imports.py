from enum import StrEnum, auto


class ImportBindingRelation(StrEnum):
    """Name every normalized relation belonging to `ImportBindingFact`."""

    FACTS = auto()
    NODES = auto()
    EVIDENCE = auto()
