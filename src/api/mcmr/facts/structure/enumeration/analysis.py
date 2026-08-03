from typing import Literal

from patos import FrozenModel

from .member import EnumMember


class EnumAnalysis(FrozenModel):
    """Retain one standard enum declaration and its literal members."""

    name: str
    kind: Literal["enum", "int_enum", "str_enum", "flag", "int_flag"]
    members: list[EnumMember] = []
    overrides_generate_next_value: bool = False
