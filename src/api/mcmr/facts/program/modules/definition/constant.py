from patos import FrozenModel
from pydantic import NonNegativeInt


class ConstantPlacement(FrozenModel):
    """Retain one module constant and statements before its valid anchor."""

    name: str
    intervening_statement_count: NonNegativeInt = 0
