from patos import FrozenModel
from pydantic import NonNegativeInt


class ReachedModule(FrozenModel):
    """Hold one module that reaches a change and its import distance."""

    module: str
    path: str
    distance: NonNegativeInt
