from typing import Annotated, Literal

from patos import FrozenModel
from pydantic import Field, NonNegativeInt

from ...foundation import NodeRef


class RepeatedStringExpression(FrozenModel):
    """Retain one nonempty string literal multiplied by a fixed integer."""

    kind: Literal["fixed-repetition"] = "fixed-repetition"
    node: NodeRef
    literal: Annotated[str, Field(min_length=1)]
    repetition_count: NonNegativeInt = 0
