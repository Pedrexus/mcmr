from typing import Annotated

from pydantic import Field, NonNegativeInt, PositiveInt

type DetectableCloneTokenCount = Annotated[int, Field(ge=40)]
type SyntaxRecord = tuple[
    str,
    str,
    PositiveInt,
    NonNegativeInt,
    PositiveInt,
    NonNegativeInt,
    list[NonNegativeInt],
]
