from patos import FrozenModel
from pydantic import NonNegativeInt

from ...foundation import NodeRef


class SetLoopFields(FrozenModel):
    """Retain initialization, loop shape, and its first source node."""

    name: str = ""
    has_unshadowed_set_initialization: bool
    loop_is_synchronous: bool
    only_effect_is_add: bool
    conditional_count: NonNegativeInt = 0
    has_else: bool = False
    initialization: NodeRef | None = None
