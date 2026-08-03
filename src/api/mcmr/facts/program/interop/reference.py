from patos import FrozenModel
from pydantic import PositiveInt


class InteropReference(FrozenModel):
    """Retain one place naming a cross-language artifact."""

    path: str
    language: str
    line: PositiveInt = 1
