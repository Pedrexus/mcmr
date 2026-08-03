from typing import TYPE_CHECKING

from ...foundation import Fact

if TYPE_CHECKING:
    from .enum import EnumMetadataMap
    from .string import StringLiteralGroup


class LiteralGroupFact(Fact):
    """Describe one group of equal or structurally related literals."""

    string_groups: list[StringLiteralGroup] = []
    enum_metadata_maps: list[EnumMetadataMap] = []
