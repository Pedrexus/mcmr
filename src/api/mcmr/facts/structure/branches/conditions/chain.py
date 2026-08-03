from patos import FrozenModel

from ....foundation import NodeRef
from .arm import ConditionalArm


class ConditionalChain(FrozenModel):
    """Retain one ordered chain of conditions and their effects."""

    subject: str = ""
    arms: list[ConditionalArm] = []
    has_fallback: bool = False
    node: NodeRef
