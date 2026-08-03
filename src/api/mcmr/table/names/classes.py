from enum import StrEnum, auto


class ClassRelation(StrEnum):
    """Name every normalized relation belonging to `ClassFact`."""

    FACTS = auto()
    CLASSES = auto()
    METHODS = auto()
    DIRECT_BASES = auto()
    CLASS_DECORATORS = auto()
    CLASS_KEYWORDS = auto()
    DIRECT_SUBCLASSES = auto()
    IMPORTING_MODULES = auto()
    METHOD_DECORATORS = auto()
    OWNER_QUALIFIED_CALLS = auto()
    COUPLED_GROUPS = auto()
    COUPLED_GROUP_SUFFIXES = auto()
    MODEL_FILES = auto()
    PROJECTIONS = auto()
    PROJECTION_ATTRIBUTES = auto()
    PROJECTION_OUTPUT_KEYS = auto()
    EVIDENCE = auto()
