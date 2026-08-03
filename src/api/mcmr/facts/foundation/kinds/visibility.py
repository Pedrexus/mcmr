from enum import StrEnum, auto


class Visibility(StrEnum):
    """Name how widely one declaration reaches across object languages.

    A provider maps its own language onto these levels through declaration keywords, Rust `pub`,
    TypeScript exports, Go identifier case, or Python's leading-underscore convention.
    """

    PUBLIC = auto()
    PROTECTED = auto()
    INTERNAL = auto()
    PRIVATE = auto()
