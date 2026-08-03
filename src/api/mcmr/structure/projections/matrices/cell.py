from patos import FrozenModel
from pydantic import NonNegativeInt


class MatrixCell(FrozenModel):
    """Hold one filled dependency cell in a design structure matrix."""

    row: NonNegativeInt
    column: NonNegativeInt
