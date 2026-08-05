from patos import FrozenModel

from ....foundation import NodeRef


class ExceptionHandler(FrozenModel):
    """Retain one caught type and the statements its handler executes."""

    caught: str = ""
    caught_is_tuple: bool = False
    alias: str = ""
    body: list[NodeRef] = []
