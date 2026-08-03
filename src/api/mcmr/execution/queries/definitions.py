from collections.abc import Sequence
from enum import StrEnum, auto


class ModelMode(StrEnum):
    """Name the two closed model operations MCMR can execute over candidates."""

    CLASSIFY = auto()
    ASSESS = auto()


type DecisionTable[Category: StrEnum] = Sequence[tuple[Category, Sequence[tuple[str, StrEnum]]]]
