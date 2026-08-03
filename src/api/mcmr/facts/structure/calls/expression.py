from enum import StrEnum, auto
from typing import TYPE_CHECKING

from patos import FrozenModel

from ...foundation import NodeRef

if TYPE_CHECKING:
    from .mapping import MappingEntry


class Expression(FrozenModel):
    """Retain one resolved expression and calls producing its value."""

    class LiteralKind(StrEnum):
        """Name the shape of a literal source expression."""

        NONE = auto()
        STRING = auto()
        NUMBER = auto()
        BOOLEAN = auto()
        MAPPING = auto()
        SEQUENCE = auto()

    text: str = ""
    qualified_name: str = ""
    literal_kind: LiteralKind = LiteralKind.NONE
    resolved_type: str = ""
    arguments: list["Expression"] = []
    entries: list["MappingEntry"] = []
    node: NodeRef | None = None
