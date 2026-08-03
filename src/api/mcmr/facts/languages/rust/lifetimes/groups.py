from typing import Literal

from patos import FrozenModel
from pydantic import PositiveInt


class LifetimeAnnotationFields(FrozenModel):
    """Retain lifetime identity, source position, and signature evidence."""

    owner: str
    kind: Literal["function", "method", "type", "trait", "alias"]
    names: list[str] = []
    line: PositiveInt = 1
    returned: list[str] = []
    receiver: str = ""
    parameters: list[str] = []
