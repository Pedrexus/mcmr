from patos import FrozenModel
from pydantic import NonNegativeInt, PositiveInt


class CommentGroupFields(FrozenModel):
    """Retain comment text, neighbors, documentation role, and measured sizes."""

    text: str = ""
    preceding_source: str = ""
    following_source: str = ""
    is_documentation: bool = False
    line_count: PositiveInt
    character_count: NonNegativeInt
    token_count: NonNegativeInt
