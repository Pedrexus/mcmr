from patos import FrozenModel

from ...foundation import NodeRef


class EnumMember(FrozenModel):
    """Retain one explicit value and standard auto result at that position."""

    name: str
    explicit_value: str | int
    standard_auto_value: str | int
    value_node: NodeRef | None = None
