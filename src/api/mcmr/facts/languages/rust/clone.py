from patos import FrozenModel
from pydantic import NonNegativeInt, PositiveInt


class CloneCall(FrozenModel):
    """Retain one copy made where a borrow could not be arranged."""

    receiver: str = ""
    owner: str = ""
    line: PositiveInt = 1
    loop_depth: NonNegativeInt = 0
