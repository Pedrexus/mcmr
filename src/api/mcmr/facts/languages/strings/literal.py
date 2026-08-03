from typing import Literal

from patos import FrozenModel
from pydantic import PositiveInt

from ...foundation import NodeRef


class LiteralStringExpression(FrozenModel):
    """Retain lexical and runtime properties of one folded string literal."""

    kind: Literal["literal"] = "literal"
    node: NodeRef
    runtime_value: str
    literal_fragment_count: PositiveInt = 1
    wraps_single_runtime_line: bool = False
