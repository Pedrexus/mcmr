from patos import FrozenModel
from pydantic import PositiveInt


class StringLiteralGroup(FrozenModel):
    """Retain exact equal strings sharing one resolved syntax role."""

    value: str
    role: str
    occurrence_count: PositiveInt
    files: list[str] = []
    is_excluded_vocabulary: bool = False
