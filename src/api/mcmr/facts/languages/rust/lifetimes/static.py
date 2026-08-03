from typing import Literal

from patos import FrozenModel
from pydantic import PositiveInt


class StaticLifetime(FrozenModel):
    """Retain one position that pins something for the whole program run."""

    owner: str = ""
    line: PositiveInt = 1
    position: Literal["demand", "supply", "bound"] = "supply"
